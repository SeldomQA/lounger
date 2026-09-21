/* Project workbench. Case selection, saved tasks and execution records have distinct homes. */
const $ = id => document.getElementById(id);
const nativeFetch = window.fetch.bind(window);
window.fetch = (url, opts = {}) => {
  const headers = new Headers(opts.headers || {});
  if (opts.method && opts.method !== 'GET') headers.set('X-Lounger-Token', document.querySelector('meta[name="lounger-token"]').content);
  return nativeFetch(url, {...opts, headers});
};
const terminal = new Set(['completed', 'error', 'cancelled', 'interrupted']);
const stateNames = {starting:'准备中',running:'运行中',finalizing:'整理结果',stopping:'正在停止',completed:'已完成',error:'执行异常',cancelled:'已取消',interrupted:'已中断'};
const outcomeNames = {passed:'通过',failed:'失败',error:'错误',skipped:'跳过',unknown:'未知'};
const validationNames = {valid:'用例有效',invalid:'需要修复',unknown:'未能校验',checking:'正在检查'};
let projectInfo = null, projectBusy = true, currentView = 'cases', taskPage = 1, runPage = 1;
let routeInitialized = false;
let tasks = [], validations = new Map(), taskLoadVersion = 0, detailVersion = 0, editorVersion = 0;
let editingTask = null, editorCases = [], editorSelected = new Set(), editorReady = false, editorTree = null, editorRemoved = 0, pickerExpanded = new Set(), pickerSearchExpanded = new Map();
let detailRun = null, detailTab = 'results', resultPage = 1, logText = '', logStart = 0, logCursor = 0, logLoading = false;
let collectionPending = Promise.resolve();
function collectApi(path, opts){
  const request=collectionPending.catch(()=>{}).then(async()=>{
    try{return await api(path,opts);}catch(error){
      if(error.code!=='project_busy')throw error;
      // A request from the previous page or another tab may still be collecting.
      // Wait for its state event rather than leaving the editor unusable or polling.
      await new Promise((resolve,reject)=>{
        const stream=new EventSource('/api/v1/project/events');
        const finish=err=>{clearTimeout(timeout);stream.close();err?reject(err):resolve();};
        const timeout=setTimeout(()=>finish(error),35000);
        stream.onmessage=event=>{const state=JSON.parse(event.data);if(state.active_run_id)finish(error);else if(!state.busy)finish();};
        stream.onerror=()=>finish(error);
      });
      return api(path,opts);
    }
  });
  collectionPending=request;return request;
}
let detailStream = null, logFollow = true, validationPending = Promise.resolve(), historyVersion = 0, resultsVersion = 0;

async function api(path, opts = {}) {
  const response = await fetch('/api/v1/' + path, opts);
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error?.message || '请求失败');
    error.code = data.error?.code; error.details = data.error?.details; throw error;
  }
  return data;
}
const body = (method, data) => ({method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
function el(tag, className = '', text = '') {const node=document.createElement(tag);node.className=className;node.textContent=text;return node;}
function notice(error = '') {$('platformNotice').textContent=error.message || error;}
function guarded(fn) {return async()=>{try{notice();await fn();}catch(error){notice(error);}};}
function button(label, fn, cls = 'btn-outline') {const node=el('button','btn '+cls,label);node.type='button';node.onclick=guarded(fn);return node;}
function badge(label, tone = '') {return el('span','badge '+tone,label);}
function runBadge(run) {return badge(run.state==='completed'?(outcomeNames[run.outcome]||'已完成'):(stateNames[run.state]||run.state),run.state==='completed'?run.outcome:run.state);}
function fmtDate(value) {return value?new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}):'—';}
function duration(ms) {return ms==null?'—':ms<1000?ms+' ms':ms<60000?(ms/1000).toFixed(1)+' 秒':Math.floor(ms/60000)+' 分 '+Math.round(ms%60000/1000)+' 秒';}
function empty(target, title, description='') {target.replaceChildren(el('div','empty-title',title),el('p','muted',description));target.classList.add('is-empty');}
function makeCell(value, cls='') {const td=el('td',cls);td.append(value instanceof Node?value:document.createTextNode(String(value)));return td;}
function table(headers) {const node=el('table','workbench-table');const head=el('thead');const row=el('tr');for(const h of headers)row.append(el('th','',h));head.append(row);node.append(head,el('tbody'));return node;}
function pager(id,data,change) {const host=$(id);host.replaceChildren();if(!data.total)return;const prev=button('上一页',()=>change(data.page-1)),next=button('下一页',()=>change(data.page+1));prev.disabled=data.page<=1;next.disabled=data.page*data.page_size>=data.total;host.append(el('span','muted',`共 ${data.total} 条 · ${data.page} / ${Math.ceil(data.total/data.page_size)} 页`),prev,next);}
function mutationButton(label, fn, disabled=false, title='') {const b=button(label,fn,'btn-accent');b.dataset.runAction='true';b.dataset.blocked=String(disabled);b.disabled=projectBusy||disabled;b.title=title;return b;}

// Keep the original sidebar, top controls and tab-based runner layout.
const legacyMain=document.querySelector('.main'), logContainer=$('historyLogContainer');
const app=el('div','workbench');
app.innerHTML=`<nav class="tab-bar app-nav" aria-label="工作台"><button class="tab-btn" id="tabLive" aria-label="实时日志" data-view="cases">📺 实时日志</button><button class="tab-btn" id="tabTasks" aria-label="测试任务" data-view="tasks">📋 测试任务</button><button class="tab-btn" id="tabHistory" aria-label="历史记录" data-view="runs">📜 历史记录</button></nav><div id="platformNotice" role="alert"></div><main class="workspace"><section id="viewCases" class="page live-page"></section><section id="viewTasks" class="page" hidden><header class="page-heading"><div><div class="eyebrow">TEST TASKS</div><h1>测试任务</h1><p class="muted">把常用用例保存为任务。代码发生变化后，先检查，再执行。</p></div><button id="newTask" class="btn btn-accent">新建任务</button></header><div class="list-toolbar"><input id="taskSearch" type="search" placeholder="搜索任务名称或描述" aria-label="搜索任务"><span id="validationSummary" class="muted"></span><button id="validateTasks" class="btn btn-outline">重新检查用例</button></div><div id="taskItems" class="table-scroll"></div><footer id="taskPager" class="pager"></footer></section>
<section id="viewRuns" class="page" hidden><header class="page-heading"><div><div class="eyebrow">EXECUTION HISTORY</div><h1>历史记录</h1><p class="muted">每次执行都有独立的结果、日志和配置快照。</p></div><button id="refreshRuns" class="btn btn-outline">刷新记录</button></header><div class="list-toolbar run-filters"><select id="taskFilter" aria-label="筛选任务"><option value="">全部任务</option></select><select id="stateFilter" aria-label="运行状态"><option value="">全部状态</option><option value="running">运行中</option><option value="completed">已完成</option><option value="error">执行异常</option><option value="cancelled">已取消</option><option value="interrupted">已中断</option></select><select id="outcomeFilter" aria-label="测试结果"><option value="">全部结果</option><option value="passed">通过</option><option value="failed">失败</option><option value="unknown">未知</option></select><label>从 <input type="date" id="dateFrom" aria-label="起始日期"></label><label>至 <input type="date" id="dateTo" aria-label="结束日期"></label><button id="resetFilters" class="btn btn-ghost">重置</button></div><div id="historyList" class="table-scroll"></div><footer id="runPager" class="pager"></footer></section>
<section id="viewRun" class="page run-page" hidden><button id="backToRuns" class="back-link">← 历史记录</button><header class="page-heading"><div><div class="title-with-status"><h1 id="runTitle"></h1><span id="runStatus"></span></div><p id="runMeta" class="muted"></p></div><div id="runActions" class="button-row"></div></header><div id="runError" class="inline-warning" hidden></div><div id="runOverview" class="metric-grid"></div><nav id="runTabs" class="detail-tabs" aria-label="执行详情"><button data-tab="results">用例结果</button><button data-tab="logs">执行日志</button><button data-tab="config">执行配置</button></nav><section id="resultPane" class="detail-pane"><div class="list-toolbar"><select id="resultFilter" aria-label="筛选用例结果"><option value="">全部结果</option><option value="unsuccessful">失败与错误</option><option value="passed">通过</option><option value="skipped">跳过</option></select><span id="resultHint" class="muted"></span></div><div id="runResults" class="results-list"></div><footer id="resultPager" class="pager"></footer></section><section id="logPane" class="detail-pane" hidden><div class="log-toolbar"><input id="logSearch" type="search" placeholder="筛选已加载日志" aria-label="搜索日志"><span id="logRange" class="muted"></span><button id="followLog" class="btn btn-outline" aria-pressed="true">跟随最新</button><button id="copyLog" class="btn btn-outline btn-copy">复制可见日志</button><a id="downloadLog" class="btn btn-outline" target="_blank" rel="noopener">完整日志 ↗</a></div><button id="earlierLogs" class="earlier-logs" hidden>向上滚动或点击载入更早日志</button><div id="copyFeedback" role="status" aria-live="polite" hidden></div><div id="logHost"></div><div id="streamStatus" class="stream-status" aria-live="polite"></div></section><section id="configPane" class="detail-pane config-pane" hidden></section></section>
</main>`;
legacyMain.querySelector('.tab-bar').remove();
legacyMain.append(app);
$('viewCases').append($('logContainer'));
$('logHost').append(logContainer);
for(const id of ['panelLive','panelHistory','panelHistoryDetail'])$(id).hidden=true;
for(const node of legacyMain.querySelectorAll('.tab-panel [id]'))if(app.querySelector('[id="'+node.id+'"]'))node.id='legacy-'+node.id;
const taskTools=el('div','toolbar task-save-toolbar');
taskTools.innerHTML='<span id="selectedCount" class="muted">已选 0 条</span><button id="saveSelection" class="btn btn-outline">保存为任务</button>';
$('tagBar').before(taskTools);
const projectBar=el('div','project-context');projectBar.innerHTML='<span id="projectInfo"></span><span id="globalStatus"></span><span id="activeRunBanner"></span>';
document.querySelector('.sidebar-header').after(projectBar);
let liveRunId=null;
$('newTask').onclick=guarded(()=>openTask());$('saveSelection').onclick=guarded(()=>openTask(null,[...selectedIds]));
document.querySelectorAll('.app-nav button').forEach(b=>b.onclick=()=>navigate(b.dataset.view));
$('refreshRuns').onclick=guarded(loadHistory);$('backToRuns').onclick=()=>navigate('runs');
$('validateTasks').onclick=guarded(()=>checkTasks(taskLoadVersion));
let searchTimer;
$('taskSearch').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{taskPage=1;loadTasks().catch(notice);},220);};
for(const id of ['taskFilter','stateFilter','outcomeFilter','dateFrom','dateTo'])$(id).onchange=()=>{runPage=1;loadHistory().catch(notice);};
$('resetFilters').onclick=()=>{for(const id of ['taskFilter','stateFilter','outcomeFilter','dateFrom','dateTo'])$(id).value='';runPage=1;loadHistory().catch(notice);};
$('resultFilter').onchange=()=>{resultPage=1;loadResults().catch(notice);};
document.querySelectorAll('#runTabs button').forEach(b=>b.onclick=()=>showDetailTab(b.dataset.tab));
$('logSearch').oninput=()=>renderLog(false);
$('followLog').onclick=()=>{logFollow=!logFollow;$('followLog').setAttribute('aria-pressed',String(logFollow));if(logFollow)renderLog(true);};
let copyFeedbackTimer;
function showCopyFeedback(message, success=false){
  clearTimeout(copyFeedbackTimer);
  const button=$('copyLog'),feedback=$('copyFeedback');
  button.textContent=success?'✓ 已复制':'复制可见日志';
  button.classList.toggle('copy-success',success);
  feedback.textContent=message;feedback.hidden=false;
  feedback.className=success?'copy-feedback success':'copy-feedback error';
  if(success)copyFeedbackTimer=setTimeout(()=>{
    button.textContent='复制可见日志';button.classList.remove('copy-success');feedback.hidden=true;
  },2500);
}
async function copyVisibleLogs(){
  const text=historyLog.getText(),button=$('copyLog');
  if(!text.trim()){showCopyFeedback('当前没有可复制的日志');return;}
  clearTimeout(copyFeedbackTimer);$('copyFeedback').hidden=true;button.classList.remove('copy-success');
  button.disabled=true;button.textContent='正在复制…';
  try{
    let copied=false;
    try{if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(text);copied=true;}}catch(_){}
    if(!copied){
      const previous=document.activeElement,field=document.createElement('textarea');
      field.value=text;field.readOnly=true;field.style.cssText='position:fixed;left:-9999px;top:0;opacity:0';
      document.body.append(field);
      try{field.focus();field.select();copied=document.execCommand('copy');}
      finally{field.remove();previous?.focus({preventScroll:true});}
    }
    if(!copied)throw new Error('clipboard unavailable');
    $('streamStatus').textContent='已复制可见日志';showCopyFeedback('已复制到剪贴板',true);
  }catch(_){const message='复制失败：浏览器限制了剪贴板访问，请打开完整日志后手动复制。';$('streamStatus').textContent=message;showCopyFeedback(message);}
  finally{button.disabled=false;}
}
$('copyLog').onclick=copyVisibleLogs;
$('earlierLogs').onclick=guarded(loadEarlierLogs);
let scrollTimer;
logContainer.addEventListener('scroll',()=>{clearTimeout(scrollTimer);scrollTimer=setTimeout(()=>{
  if(logContainer.scrollTop===0&&logStart>0&&!logLoading&&!$('logSearch').value)loadEarlierLogs().catch(notice);
},120);});

function navigate(view, id=null, updateHash=true) {
  routeInitialized=true;
  if(view==='cases'&&(projectInfo?.active_run_id||liveRunId)){id=projectInfo?.active_run_id||liveRunId;view='run';}
  currentView=view;
  for(const [name,node] of Object.entries({cases:'viewCases',tasks:'viewTasks',runs:'viewRuns',run:'viewRun'}))$(node).hidden=name!==view;
  document.querySelectorAll('.app-nav button').forEach(b=>{const active=b.dataset.view===(view==='run'?(id===liveRunId||id===projectInfo?.active_run_id?'cases':'runs'):view);b.classList.toggle('active',active);b.setAttribute('aria-current',active?'page':'false');});
  if(view!=='run'){detailVersion++;if(detailStream){detailStream.close();detailStream=null;}}
  if(updateHash)history.replaceState(null,'','#'+(view==='run'?'runs/'+id:view));
  if(view==='tasks')loadTasks().catch(notice);
  if(view==='runs')loadHistory().catch(notice);
  if(view==='run')viewHistoryRun(id,id===liveRunId||id===projectInfo?.active_run_id).catch(notice);
  if(view==='cases')updateSelection();
}
switchTab=tab=>navigate(tab==='history'?'runs':tab==='live'?'cases':tab);
window.addEventListener('hashchange',()=>restoreRoute());
function restoreRoute(){const [view,id]=location.hash.slice(1).split('/');navigate(view==='runs'&&id?'run':['cases','tasks','runs'].includes(view)?view:'cases',id,false);}
function updateSelection(){
  $('selectedCount').textContent=`已选 ${selectedIds.size} 条`;
  $('saveSelection').disabled=selectedIds.size===0;
}
const originalRenderTree=renderTree;renderTree=function(){originalRenderTree();updateSelection();};
const originalToggleCase=toggleCase;toggleCase=function(id,event){originalToggleCase(id,event);updateSelection();};

async function loadTasks(){
  const generation=++taskLoadVersion;
  $('taskItems').classList.remove('is-empty');$('taskItems').replaceChildren(el('p','loading','正在加载任务…'));
  const data=await api('tasks?page='+taskPage+'&search='+encodeURIComponent($('taskSearch').value));
  if(generation!==taskLoadVersion||currentView!=='tasks')return;
  tasks=data.items;validations=new Map(tasks.map(t=>[t.id,{status:'checking'}]));renderTasks();
  pager('taskPager',data,async page=>{taskPage=page;await loadTasks();});
  await checkTasks(generation);
}
function renderTasks(){
  const host=$('taskItems');host.classList.remove('is-empty');host.replaceChildren();
  if(!tasks.length){empty(host,$('taskSearch').value?'没有匹配的任务':'还没有测试任务','点击「新建任务」，用勾选的方式组合常用测试用例。');return;}
  const grid=table(['任务','用例健康状态','最近一次执行','操作']);
  for(const task of tasks){
    const v=validations.get(task.id)||{status:'unknown'},row=el('tr');row.dataset.taskId=task.id;
    const name=el('div');name.append(button(task.name,()=>openTask(task),'text-button'),el('p','muted row-description',task.description||'暂无描述'));
    const health=el('div','cell-stack');health.append(badge(validationNames[v.status],v.status),el('span','muted',`${task.selection.nodeids.length} 条用例${v.missing?.length?' · '+v.missing.length+' 条失效':''}`));
    if(v.status==='unknown')health.title=v.reason||'当前无法收集用例，尚不能判断是否失效';
    const latest=el('div','cell-stack');if(task.last_run){latest.append(runBadge(task.last_run),button(fmtDate(task.last_run.started_at),()=>navigate('run',task.last_run.id),'text-button muted'));}else latest.append(el('span','muted','尚未执行'));
    const actions=el('div','button-row');
    if(v.status==='invalid')actions.append(button('修复用例',()=>openTask(task),'btn-warning'));
    else actions.append(mutationButton('运行任务',()=>runTask(task),v.status!=='valid',v.status==='unknown'?'请先完成用例检查':''));
    actions.append(button('编辑',()=>openTask(task),'btn-ghost'));
    const more=el('details','action-menu');more.append(el('summary','btn btn-ghost','更多'));
    const menu=el('div','menu-content');menu.append(button('历史记录',()=>{setTaskFilter(task);navigate('runs');},'btn-ghost'),button('删除任务',async()=>{if(await confirmAction('删除「'+task.name+'」？','任务的历史执行记录仍会保留。')){await api('tasks/'+task.id,{method:'DELETE'});await loadTasks();}},'btn-danger'));more.append(menu);actions.append(more);
    row.append(makeCell(name),makeCell(health),makeCell(latest),makeCell(actions));grid.tBodies[0].append(row);
  }
  host.append(grid);setRunButtonsDisabled(projectBusy);
}
function checkTasks(generation){
  validationPending = validationPending.catch(()=>{}).then(()=>performTaskCheck(generation));
  return validationPending;
}
async function performTaskCheck(generation){
  if(generation!==taskLoadVersion)return;
  if(!tasks.length){$('validationSummary').textContent='';return;}
  $('validateTasks').disabled=true;$('validationSummary').textContent='正在根据当前代码检查任务用例…';
  try{
    const result=await collectApi('tasks/validate',body('POST',{task_ids:tasks.map(t=>t.id)}));
    if(generation!==taskLoadVersion||currentView!=='tasks')return;
    for(const item of result.items){if(tasks.some(t=>t.id===item.id&&t.revision===item.revision))validations.set(item.id,item);}
    renderTasks();const invalid=result.items.filter(i=>i.status==='invalid').length,unknown=result.items.some(i=>i.status==='unknown');
    $('validationSummary').textContent=unknown?'暂时无法校验，任务未被判定为失效':`${invalid?invalid+' 个任务需要修复':'本页任务用例均有效'} · 检查于 ${fmtDate(result.checked_at)}`;
  }finally{$('validateTasks').disabled=false;await updateRunStatus();}
}
async function runTask(task){
  try {const run=await api('tasks/'+task.id+'/runs',{...body('POST',{verbosity:currentVerbosity}),headers:{'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()}});liveRunId=run.id;navigate('run',run.id);}
  catch(error){if(error.code==='selection_stale'){notice('代码已发生变化，请修复标出的失效用例后再运行。');await openTask(task);}else throw error;}
}
function setTaskFilter(task){const select=$('taskFilter');if(![...select.options].some(o=>o.value===task.id))select.add(new Option(task.name,task.id));select.value=task.id;runPage=1;}

// Task editor: metadata + searchable, grouped picker + explicit invalid-reference repair.
const dialog=el('dialog','task-editor');dialog.id='taskDialog';dialog.innerHTML=`<form id="taskForm"><header class="editor-header"><div><h2 id="taskTitle">新建任务</h2><p class="muted">从当前项目中选择用例，无需填写用例路径。</p></div><button id="closeTask" type="button" class="icon-button" aria-label="关闭任务编辑">×</button></header><div class="editor-meta"><label>任务名称 <span class="required">*</span><input id="taskName" required maxlength="128" placeholder="例如：订单流程冒烟"></label><label>描述<input id="taskDescription" maxlength="10000" placeholder="说明这个任务验证什么（可选）"></label></div><div class="editor-body"><section class="picker"><div class="picker-toolbar"><input id="pickerSearch" type="search" placeholder="搜索用例、文件或描述" aria-label="搜索可选用例"><button id="selectVisible" type="button" class="btn btn-ghost">勾选搜索结果</button></div><div class="picker-selection-bar"><span id="pickerState" class="muted"></span><strong id="editorCount">已勾选 0 条用例</strong><button id="clearSelection" type="button" class="btn btn-ghost">清空勾选</button></div><div id="missingWarning" class="inline-warning" hidden></div><div id="casePickerList" class="picker-list"></div></section></div><div id="taskError" class="inline-warning" role="alert" hidden></div><footer class="editor-footer"><details class="execution-options"><summary>执行选项</summary><label>日志级别<select id="taskVerbosity"><option value="quiet">静默</option><option value="normal">标准</option><option value="verbose">详细</option><option value="full">完整</option></select></label><label class="checkbox-label"><input id="taskReport" type="checkbox">生成 HTML 报告</label></details><span id="saveHint" class="muted"></span><button id="cancelTask" type="button" class="btn btn-outline">取消</button><button id="saveTask" class="btn btn-accent" type="submit">保存任务</button></footer></form>`;document.body.append(dialog);
$('closeTask').onclick=$('cancelTask').onclick=()=>{editorVersion++;dialog.close();};
$('pickerSearch').oninput=()=>{pickerSearchExpanded.clear();renderPicker();};
$('selectVisible').onclick=()=>{for(const c of visibleCases())editorSelected.add(c.nodeid);renderPicker();renderSelected();};
$('clearSelection').onclick=()=>{editorSelected.clear();renderPicker();renderSelected();};
function visibleCases(){const q=$('pickerSearch').value.toLowerCase().trim();return editorCases.filter(c=>!q||[c.file,c.nodeid,c.name,c.description].join(' ').toLowerCase().includes(q));}
async function openTask(task=null, initial=[]){
  const generation=++editorVersion;editingTask=task;editorSelected=new Set(task?.selection.nodeids||initial);editorReady=false;editorTree=null;editorRemoved=0;pickerExpanded.clear();pickerSearchExpanded.clear();editorCases=[];
  $('taskTitle').textContent=task?'编辑任务':'新建任务';$('taskName').value=task?.name||'';$('taskDescription').value=task?.description||'';$('pickerSearch').value='';
  $('taskVerbosity').value=task?.options.verbosity||currentVerbosity;$('taskReport').checked=task?.options.html_report??reportEnabled;$('taskError').hidden=true;
  $('casePickerList').replaceChildren(el('p','loading','正在收集当前项目的用例…'));$('pickerState').textContent='';renderSelected();if(!dialog.open)dialog.showModal();
  try{
    await validationPending.catch(()=>{});if(generation!==editorVersion||!dialog.open)return;
    const data=await collectApi('cases/refresh',{method:'POST'});if(generation!==editorVersion||!dialog.open)return;
    editorCases=data.flat;editorTree=data.tree;editorReady=true;
    const known=new Set(editorCases.map(c=>c.nodeid));
    editorRemoved=[...editorSelected].filter(id=>!known.has(id)).length;
    editorSelected=new Set([...editorSelected].filter(id=>known.has(id)));$('pickerState').textContent=`当前项目 ${editorCases.length} 条用例`;
    renderPicker();renderSelected();
  }catch(error){if(generation!==editorVersion)return;$('casePickerList').replaceChildren(el('p','inline-warning','无法收集用例：'+error.message),button('重新加载',()=>openTask(task,initial)));$('pickerState').textContent='未能校验，不会把已有用例误判为删除';renderSelected();}
  finally{await updateRunStatus();}
}
function renderPicker(){
  const host=$('casePickerList'),scroll=host.scrollTop;
  host.replaceChildren();host.classList.remove('is-empty');
  const visible=new Set(visibleCases().map(c=>c.nodeid)),searching=!!$('pickerSearch').value.trim();
  function branch(node,depth){
    const children=(node.children||[]).map(child=>branch(child,depth+1)).filter(Boolean);
    const cases=(node.cases||[]).filter(c=>visible.has(c.nodeid));
    const ids=node.type==='file'?cases.map(c=>c.nodeid):children.flatMap(child=>child.ids);
    if(!ids.length)return null;
    const key=nodeKey(node),group=el('details','picker-tree-group'),heading=el('summary','tree-node '+(node.type==='dir'?'tree-dir':'tree-file'));
    group.dataset.editorNode=key;
    group.open=searching?(pickerSearchExpanded.get(key)??true):pickerExpanded.has(key);
    group.addEventListener('toggle',()=>{
      if(!group.isConnected)return;
      if(searching)pickerSearchExpanded.set(key,group.open);
      else if(group.open)pickerExpanded.add(key);else pickerExpanded.delete(key);
    });
    heading.style.paddingLeft=(8+depth*18)+'px';
    const check=document.createElement('input');check.type='checkbox';
    check.setAttribute('aria-label',(node.type==='dir'?'选择目录 ':'选择文件 ')+node.relpath);
    check.checked=ids.every(id=>editorSelected.has(id));check.indeterminate=!check.checked&&ids.some(id=>editorSelected.has(id));
    check.onclick=event=>event.stopPropagation();
    check.onchange=()=>{for(const id of ids)check.checked?editorSelected.add(id):editorSelected.delete(id);renderPicker();renderSelected();};
    heading.append(el('span','tree-toggle','▶'),check,el('span','tree-icon',node.type==='dir'?'📁':'📄'),el('span','tree-label',node.name),el('span','count',String(ids.length)));
    group.append(heading);
    if(node.type==='dir')for(const child of children)group.append(child.element);
    else for(const c of cases){
      const label=el('label','tree-node tree-case picker-tree-case');label.style.paddingLeft=(26+(depth+1)*18)+'px';
      const input=document.createElement('input');input.type='checkbox';input.checked=editorSelected.has(c.nodeid);input.setAttribute('aria-label','选择用例 '+c.nodeid);
      input.onchange=()=>{input.checked?editorSelected.add(c.nodeid):editorSelected.delete(c.nodeid);renderPicker();renderSelected();};
      const text=el('span','tree-label',c.description?.split('\n')[0]||c.name);text.title=c.nodeid;
      label.append(input,el('span','tree-icon','🧪'),text);group.append(label);
    }
    return {element:group,ids};
  }
  for(const node of editorTree?.children||[]){const result=branch(node,0);if(result)host.append(result.element);}
  if(!host.children.length)empty(host,'没有匹配的用例','尝试更换搜索关键词。');
  host.scrollTop=scroll;
}
function renderSelected(){
  $('editorCount').textContent=`已勾选 ${editorSelected.size} 条用例`;
  $('missingWarning').hidden=!editorRemoved;
  $('missingWarning').textContent=`${editorRemoved} 条原用例已改名、删除或未被收集，已取消勾选。保存后更新任务。`;
  $('saveTask').disabled=!editorReady||!editorSelected.size;
  $('selectVisible').disabled=!editorReady;
  $('saveHint').textContent=!editorReady?'等待用例校验':!editorSelected.size?'请至少勾选一条用例':'';
}
$('taskForm').onsubmit=async event=>{
  event.preventDefault();if($('saveTask').disabled)return;$('saveTask').disabled=true;
  try{
    const data={name:$('taskName').value,description:$('taskDescription').value,selection:{type:'nodeids',nodeids:[...editorSelected]},options:{verbosity:$('taskVerbosity').value,html_report:$('taskReport').checked}};
    if(editingTask)data.revision=editingTask.revision;
    await api('tasks'+(editingTask?'/'+editingTask.id:''),body(editingTask?'PATCH':'POST',data));editorVersion++;dialog.close();navigate('tasks');
  }catch(error){$('taskError').hidden=false;$('taskError').textContent=error.code==='revision_conflict'?'任务已在其他页面修改，请关闭后重新打开编辑。你的本次选择尚未保存。':error.message;renderSelected();}
};
function confirmAction(title, description){return new Promise(resolve=>{const prompt=el('dialog','confirm-dialog');prompt.append(el('h2','',title),el('p','muted',description));const actions=el('div','button-row');const finish=value=>{prompt.close();prompt.remove();resolve(value);};actions.append(button('取消',()=>finish(false)),button('确认删除',()=>finish(true),'btn-danger'));prompt.append(actions);prompt.oncancel=e=>{e.preventDefault();finish(false);};document.body.append(prompt);prompt.showModal();});}

async function loadHistory(){
  const generation=++historyVersion;
  const filters=new URLSearchParams({page:runPage});for(const [key,id] of [['task_id','taskFilter'],['state','stateFilter'],['outcome','outcomeFilter'],['date_from','dateFrom'],['date_to','dateTo']])if($(id).value)filters.set(key,$(id).value);
  const route=filters.toString();$('historyList').classList.remove('is-empty');$('historyList').replaceChildren(el('p','loading','正在加载执行记录…'));
  const [data,taskData]=await Promise.all([api('runs?'+route),api('tasks?page_size=100')]);if(currentView!=='runs'||generation!==historyVersion)return;
  const lastPage=Math.max(1,Math.ceil(data.total/data.page_size));if(runPage>lastPage){runPage=lastPage;return loadHistory();}
  for(const task of taskData.items)if(![...$('taskFilter').options].some(o=>o.value===task.id))$('taskFilter').add(new Option(task.name,task.id));
  const host=$('historyList');host.replaceChildren();if(!data.items.length){empty(host,'没有执行记录','调整筛选条件，或从用例、任务页面发起一次执行。');pager('runPager',data,()=>{});return;}
  const grid=table(['任务 / 执行','结果','用例统计','开始时间','耗时','']);
  for(const run of data.items){const row=el('tr');row.dataset.runId=run.id;const title=el('div');title.append(button(run.task_name_snapshot||'临时执行',()=>navigate('run',run.id),'text-button'),el('p','muted',`#${run.id.slice(0,8)} · ${run.request.selection.nodeids.length} 条选中用例`));
    const counts=el('div','count-inline');for(const [key,label] of [['passed','通过'],['failed','失败'],['error','错误']])counts.append(el('span',key,`${label} ${run.counts?.[key]??'—'}`));
    const actions=el('div','button-row');
    const remove=button('删除',async()=>{if(await confirmAction('删除这次执行？','执行记录、日志和报告将一起删除，任务定义不受影响。')){await api('runs/'+run.id,{method:'DELETE'});if(liveRunId===run.id)liveRunId=null;await loadHistory();}},'btn-danger');
    remove.disabled=!terminal.has(run.state);if(remove.disabled)remove.title='执行结束后可删除';
    actions.append(button(terminal.has(run.state)?'查看详情':'查看执行',()=>navigate('run',run.id),'text-button'),remove);
    row.append(makeCell(title),makeCell(runBadge(run)),makeCell(counts),makeCell(fmtDate(run.started_at),'nowrap'),makeCell(duration(run.duration_ms),'nowrap'),makeCell(actions));grid.tBodies[0].append(row);
  }host.append(grid);pager('runPager',data,async page=>{runPage=page;await loadHistory();});
}
async function viewHistoryRun(id,preferLogs=false){
  $('viewRun').classList.toggle('live-detail',preferLogs);
  const version=++detailVersion;if(detailStream){detailStream.close();detailStream=null;}detailRun=null;logText='';logStart=0;logCursor=0;resultPage=1;logFollow=true;$('logSearch').value='';$('resultFilter').value='';historyLog.clear();
  $('runTitle').textContent='正在加载执行…';$('runOverview').replaceChildren();$('runResults').replaceChildren();$('streamStatus').textContent='';
  const run=await api('runs/'+id);if(version!==detailVersion||currentView!=='run')return;detailRun=run;renderRunHeader();showDetailTab(preferLogs||!terminal.has(run.state)?'logs':'results');
  const batch=await api('runs/'+id+'/logs?tail=1');if(version!==detailVersion)return;
  logText=batch.text;logStart=batch.start;logCursor=batch.cursor;renderLog(true);
  if(!terminal.has(run.state))connectStream(id,version);
  await loadResults(version);
}
function reportLink(run){return run.report_path?'/api/v1/runs/'+run.id+'/artifacts/'+run.report_path:run.legacy_report?'/api/report/'+run.id:null;}
function renderRunHeader(){
  const run=detailRun;if(!run)return;$('runTitle').textContent=run.task_name_snapshot||'临时执行';$('runStatus').replaceChildren(runBadge(run));$('runMeta').textContent=`#${run.id.slice(0,8)} · ${fmtDate(run.started_at)} · 耗时 ${duration(run.duration_ms)}`;
  $('runError').hidden=!run.error_message;$('runError').textContent=run.error_message||'';
  const actions=$('runActions');actions.replaceChildren();if(!terminal.has(run.state))actions.append(button(run.state==='stopping'?'正在停止…':'停止执行',()=>api('runs/'+run.id+'/stop',{method:'POST'}),'btn-danger'));
  else actions.append(mutationButton('再次执行',async()=>{const next=await api('runs',{...body('POST',{rerun_id:run.id}),headers:{'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()}});liveRunId=next.id;navigate('run',next.id);}));
  if(reportLink(run)){const link=el('a','btn btn-outline btn-report','HTML 报告 ↗');link.id='runReportBtn';link.href=reportLink(run);link.target='_blank';link.rel='noopener';actions.append(link);}
  if(terminal.has(run.state))actions.append(button('删除记录',async()=>{if(await confirmAction('删除这次执行？','执行记录、日志和报告将一起删除，任务定义不受影响。')){await api('runs/'+run.id,{method:'DELETE'});if(liveRunId===run.id)liveRunId=null;navigate('runs');}},'btn-danger'));
  const metrics=$('runOverview');metrics.replaceChildren();for(const [key,title] of [['total','报告用例'],['passed','通过'],['failed','失败'],['error','错误'],['skipped','跳过']]){const card=el('div','metric '+key);card.append(el('span','muted',title),el('strong','',String(run.counts?.[key]??'—')));metrics.append(card);}
  const config=$('configPane');config.replaceChildren();const list=el('dl','config-list');for(const [key,value] of [['任务版本',run.task_revision?'第 '+run.task_revision+' 版':'临时选择'],['Python 环境',run.python_path||'未记录'],['代码版本',run.git?.commit||'未记录'],['工作区',run.git?.dirty?'有未提交修改':'未记录修改'],['日志级别',run.request.options.verbosity]])list.append(el('dt','',key),el('dd','',value));config.append(list,el('h3','','执行时的用例快照'),el('p','muted','后续修改任务，不会改变这次执行的用例与配置。'),el('pre','snapshot',run.request.selection.nodeids.join('\n')));
  if(run.state==='interrupted'&&projectInfo?.blocked.some(b=>b.run_id===run.id))config.append(button('已检查并停止残留进程',async()=>{await api('runs/'+run.id+'/acknowledge',body('POST',{processes_inspected:true}));await updateRunStatus();notice('恢复保护已解除。');}));
  $('downloadLog').href='/api/v1/runs/'+run.id+'/artifacts/output.log';setRunButtonsDisabled(projectBusy);
}
function showDetailTab(tab){detailTab=tab;for(const [name,id] of [['results','resultPane'],['logs','logPane'],['config','configPane']])$(id).hidden=name!==tab;document.querySelectorAll('#runTabs button').forEach(b=>{b.classList.toggle('active',b.dataset.tab===tab);b.setAttribute('aria-selected',String(b.dataset.tab===tab));});if(tab==='logs')requestAnimationFrame(()=>renderLog(logFollow));}
async function loadResults(version=detailVersion){
  if(!detailRun)return;const generation=++resultsVersion;const run=detailRun;const data=await api('runs/'+run.id+'/results?page='+resultPage+'&outcome='+$('resultFilter').value);if(version!==detailVersion||generation!==resultsVersion)return;
  const host=$('runResults');host.classList.remove('is-empty');host.replaceChildren();$('resultHint').textContent=run.result_status==='ready'?`共 ${data.total} 条结果`:run.result_status==='pending'?'执行结束后生成用例结果':run.result_status==='partial'?'以下为已生成的部分结果':'本次没有可用的结构化报告，可查看执行日志';
  if(!data.items.length)empty(host,!terminal.has(run.state)?'测试正在执行':'暂无匹配结果',!terminal.has(run.state)?'切换到执行日志查看实时进度。':'可以调整结果筛选，或查看执行日志。');
  for(const result of data.items){const row=el('details','result-row');row.open=['failed','error'].includes(result.outcome);const summary=el('summary');summary.append(badge(outcomeNames[result.outcome]||result.outcome,result.outcome),el('strong','',result.name),el('span','muted result-class',result.classname),el('span','muted',duration(result.duration_ms)));const content=el('div','result-content');content.append(el('pre','',result.failure_text||result.stdout||result.stderr||'该用例没有附加日志。'));for(const key of ['stdout','stderr'])if(result[key+'_path']){const link=el('a','text-button',key==='stdout'?'完整标准输出 ↗':'完整错误输出 ↗');link.href='/api/v1/runs/'+run.id+'/artifacts/'+result[key+'_path'];link.target='_blank';link.rel='noopener';content.append(link);}row.append(summary,content);host.append(row);}
  pager('resultPager',data,async page=>{resultPage=page;await loadResults();});
}
function renderLog(follow=false){
  const oldTop=logContainer.scrollTop,query=$('logSearch').value.toLowerCase();let lines=logText.replace(/\x1b\[[0-9;]*m/g,'').split('\n');if(query)lines=lines.filter(line=>line.toLowerCase().includes(query));historyLog.setLines(lines);if(!follow||query)logContainer.scrollTop=oldTop;historyLog.refresh();
  $('earlierLogs').hidden=logStart===0;$('logRange').textContent=logStart>0?'显示最近日志 · 可向上载入更早内容':query?`匹配 ${lines.length} 行`:'已加载完整起始日志';$('followLog').setAttribute('aria-pressed',String(logFollow));
}
async function loadEarlierLogs(){
  if(logLoading||!logStart||!detailRun)return;logLoading=true;const version=detailVersion,top=logContainer.scrollTop,oldHeight=logContainer.scrollHeight;$('earlierLogs').disabled=true;
  try{const batch=await api('runs/'+detailRun.id+'/logs?before='+logStart);if(version!==detailVersion)return;logText=batch.text+logText;logStart=batch.start;logFollow=false;renderLog(false);logContainer.scrollTop=top+logContainer.scrollHeight-oldHeight;}
  finally{logLoading=false;$('earlierLogs').disabled=false;}
}
function connectStream(id,version){
  detailStream=new EventSource('/api/v1/runs/'+id+'/events?cursor='+logCursor);
  detailStream.onopen=()=>{$('streamStatus').textContent='实时连接正常 · 离开此页不会中断执行';};
  detailStream.onerror=()=>{if(version===detailVersion)$('streamStatus').textContent='连接暂时断开，正在续传。后台执行仍继续。';};
  detailStream.onmessage=async event=>{
    if(version!==detailVersion)return;const msg=JSON.parse(event.data);
    if(msg.text&&msg.cursor>logCursor){logText+=msg.text;logCursor=msg.cursor;
      if(logText.length>4*1024*1024){const removed=logText.slice(0,logText.length-2*1024*1024);logStart+=new TextEncoder().encode(removed).length;logText=logText.slice(removed.length);}
      if(detailTab==='logs')renderLog(logFollow&&historyLog.atBottom());}
    if(msg.status){detailRun.state=msg.status;$('runStatus').replaceChildren(runBadge(detailRun));}
    if(msg.done){detailStream.close();detailStream=null;$('streamStatus').textContent='执行已结束 · 日志已保存';const run=await api('runs/'+id);if(version!==detailVersion)return;detailRun=run;renderRunHeader();await loadResults(version);await updateRunStatus();}
  };
}
startRun=async function(nodeids){try{if(!nodeids.length){notice('请先选择用例。');return;}const run=await api('runs',{...body('POST',{selection:{type:'nodeids',nodeids},options:{verbosity:currentVerbosity,html_report:reportEnabled}}),headers:{'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()}});liveRunId=run.id;navigate('run',run.id);}catch(error){notice(error.code==='selection_stale'?'所选用例已变化，请刷新用例列表后重新选择。':error);}};
setRunButtonsDisabled=function(disabled){projectBusy=disabled;for(const id of ['runSelectedBtn','runAllBtn'])$(id).disabled=disabled;document.querySelectorAll('[data-run-action]').forEach(b=>b.disabled=disabled||b.dataset.blocked==='true');};
let projectStream=null, seenSourceRevision=0, pendingSourceRefresh=false, sourceRefreshTimer=null;
function applyProject(info){
  projectInfo=info;
  $('projectInfo').textContent=info.name;$('projectInfo').title=info.path+'\nPython: '+info.python;
  $('globalStatus').textContent=info.busy?'忙碌':'就绪';$('statusText').textContent=info.busy?'执行 / 收集中':'就绪';
  $('statusDot').classList.toggle('running',info.busy);setRunButtonsDisabled(info.busy);
  const banner=$('activeRunBanner');banner.replaceChildren();
  if(info.active_run_id)banner.append(button('● 正在执行 · 查看',()=>navigate('run',projectInfo.active_run_id),'active-run-link'));
  if(info.warnings.length||info.blocked.length)notice([...info.warnings,...info.blocked.map(b=>b.message)].join('\n'));
  if(info.sources_revision!==seenSourceRevision){
    seenSourceRevision=info.sources_revision;pendingSourceRefresh=true;
    if(dialog.open){editorReady=false;renderSelected();$('taskError').hidden=false;$('taskError').textContent='项目文件已变化，请重新打开编辑器以校验用例。本次未保存的选择仍保留。';}
  }
  if(pendingSourceRefresh&&!info.busy){
    clearTimeout(sourceRefreshTimer);
    sourceRefreshTimer=setTimeout(async()=>{
      if(projectBusy)return;
      pendingSourceRefresh=false;
      await loadCases();
      if(currentView==='tasks')await checkTasks(taskLoadVersion).catch(notice);
    },500);
  }
}
updateRunStatus=async function(){try{applyProject(await api('project'));}catch(error){notice(error);}};
function connectProjectEvents(){
  projectStream=new EventSource('/api/v1/project/events');
  projectStream.onmessage=event=>applyProject(JSON.parse(event.data));
  projectStream.onerror=()=>{$('globalStatus').textContent='连接中断，正在重连';setRunButtonsDisabled(true);};
}
window.addEventListener('pagehide',()=>{projectStream?.close();detailStream?.close();clearTimeout(sourceRefreshTimer);});
window.addEventListener('pageshow',event=>{if(event.persisted)connectProjectEvents();});
loadCases=async function(refresh=false){setRunButtonsDisabled(true);try{const data=await collectApi(refresh?'cases/refresh':'cases/tree',refresh?{method:'POST'}:{});allCases=data.flat;caseTree=data.tree;renderTree();renderTagBar();}catch(error){notice(error);}finally{await updateRunStatus();}};
refreshCases=()=>loadCases(true);
(async()=>{
  await updateRunStatus();if(projectInfo){try{for(const key of [EXPANDED_NODES_KEY,SIDEBAR_WIDTH_KEY,FAVORITES_KEY,REPORT_ENABLED_KEY])if(localStorage.getItem(key+'.'+projectInfo.id)===null&&localStorage.getItem(key)!==null)localStorage.setItem(key+'.'+projectInfo.id,localStorage.getItem(key));}catch(_){}
    EXPANDED_NODES_KEY+='.'+projectInfo.id;SIDEBAR_WIDTH_KEY+='.'+projectInfo.id;FAVORITES_KEY+='.'+projectInfo.id;REPORT_ENABLED_KEY+='.'+projectInfo.id;expandedNodes=loadExpandedNodes();favorites=loadFavorites();reportEnabled=loadReportEnabled();$('reportToggle').checked=reportEnabled;}
  applySidebarWidth(loadSidebarWidth());await loadCases();
  // Initial collection may finish after the user has already navigated.
  if(!routeInitialized)restoreRoute();
  connectProjectEvents();
})().catch(notice);
