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
.sidebar { width: 420px; min-width: 320px; background: var(--surface);
  border-right: 1px solid var(--border); display: flex; flex-direction: column; }
.sidebar-header { padding: 16px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 10px; }
.sidebar-header h1 { font-size: 18px; font-weight: 600; }
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
.case-list { flex: 1; overflow-x: hidden; overflow-y: auto; padding: 4px 0; }
/* ── tree nodes ── */
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
</style>
</head>
<body>

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
    <button class="btn btn-green" onclick="runSelected()" style="flex:1">▶ 执行选中</button>
    <button class="btn btn-accent" onclick="runAll()" style="flex:1">▶▶ 执行全部</button>
  </div>
  <div class="case-list" id="caseList">
    <div class="empty-state">⏳ 正在收集用例...</div>
  </div>
</div>

<div class="main">
  <div class="main-header">
    <span class="status-dot" id="statusDot"></span>
    <span id="statusText">就绪</span>
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
  <div class="log-container" id="logContainer">
    <div class="log-placeholder">
      <div class="icon">📋</div>
      <div>选择左侧用例，点击「执行」开始</div>
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
  if (document.getElementById('search').value) {
    filterCases();
  }
}

function renderNode(node, depth) {
  const indent = depth * 18;
  let html = '';

  if (node.type === 'dir') {
    const hasKids = node.children && node.children.length > 0;
    html += '<div class="tree-node tree-dir open" onclick="toggleTreeNode(this)" style="padding-left:' + indent + 'px">';
    html += '<span class="tree-toggle' + (hasKids ? '' : ' leaf') + '">▶</span>';
    html += '<span class="tree-icon">📁</span>';
    html += '<span class="tree-label" title="' + esc(node.relpath || node.name) + '">' + esc(node.name);
    html += ' <span class="count">(' + node.total_cases + ')</span></span>';
    html += '</div>';
    if (hasKids) {
      html += '<div class="tree-children show">';
      for (const child of node.children) {
        html += renderNode(child, depth + 1);
      }
      html += '</div>';
    }
  } else if (node.type === 'file') {
    const hasCases = node.cases && node.cases.length > 0;
    html += '<div class="tree-node tree-file open" onclick="toggleTreeNode(this)" style="padding-left:' + indent + 'px">';
    html += '<span class="tree-toggle' + (hasCases ? '' : ' leaf') + '">▶</span>';
    html += '<span class="tree-icon">📄</span>';
    html += '<span class="tree-label" title="' + esc(node.relpath || node.name) + '">' + esc(node.name);
    if (hasCases) html += ' <span class="count">(' + node.case_count + ')</span>';
    html += '</span>';
    if (hasCases) {
      const idsJson = JSON.stringify(node.cases.map(c => c.nodeid));
      html += '<button class="run-btn" data-ids=\'' + idsJson + '\' onclick="event.stopPropagation(); runFile(this.dataset.ids)" title="运行此文件全部用例">▶▶</button>';
    }
    html += '</div>';
    if (hasCases) {
      html += '<div class="tree-children show">';
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
  html += '<button class="run-btn" onclick="event.stopPropagation(); runSingle(\'' + esc(c.nodeid) + '\')">▶</button>';
  html += '</div>';
  return html;
}

function toggleTreeNode(el) {
  el.classList.toggle('open');
  const children = el.nextElementSibling;
  if (children && children.classList.contains('tree-children')) {
    children.classList.toggle('show');
  }
}

function toggleCase(nodeid, ev) {
  if (selectedIds.has(nodeid)) {
    selectedIds.delete(nodeid);
  } else {
    selectedIds.add(nodeid);
  }
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

function filterCases() {
  const q = document.getElementById('search').value.toLowerCase();
  const container = document.getElementById('caseList');
  const allRows = container.querySelectorAll('.tree-node');
  const allGroups = container.querySelectorAll('.tree-children');

  allRows.forEach(row => {
    if (row.classList.contains('tree-case')) {
      const label = (row.querySelector('.tree-label')?.textContent || '').toLowerCase();
      row.style.display = (!q || label.includes(q)) ? '' : 'none';
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
    } else if (q) {
      group.style.display = 'none';
      group.classList.remove('show');
    } else {
      group.style.display = '';
      group.classList.add('show');
      const header = group.previousElementSibling;
      if (header && header.classList.contains('tree-node')) {
        header.classList.add('open');
        header.style.display = '';
      }
    }
  });

  if (q) {
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
  const ids = JSON.parse(nodeidsStr);
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
      loadCases();
    }
  };

  eventSource.onerror = function() {
    if (eventSource && eventSource.readyState === EventSource.CLOSED) {
      eventSource = null;
    }
  };
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
    // fallback for older browsers or non-HTTPS
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

loadCases();
</script>
</body>
</html>"""
