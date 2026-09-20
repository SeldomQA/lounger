"""Behavioral workbench flows, including task repair and non-disruptive live monitoring."""

import secrets
import threading

import pytest

from lounger.web_runner.api import PlatformHandler
from lounger.web_runner.context import ProjectContext
from lounger.web_runner.manager import RunManager
from lounger.web_runner.server import _ThreadingHTTPServer


@pytest.fixture
def workbench(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "test_demo.py").write_text('def test_ok():\n    print("browser test log")\n    assert True\n')
    manager = RunManager(ProjectContext.create(str(tmp_path)))
    manager.watch()
    server = _ThreadingHTTPServer(("127.0.0.1", 0), PlatformHandler)
    server.manager, server.session_token = manager, secrets.token_urlsafe(32)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(10000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(f"http://127.0.0.1:{server.server_address[1]}")
            yield page, manager, errors, tmp_path
        finally:
            page.screenshot(path=str(tmp_path / "final.png"), full_page=True)
            browser.close()
            server.shutdown()
            manager.close()
            server.server_close()
            thread.join()


def save_smoke_task(page):
    from playwright.sync_api import expect

    page.get_by_role("button", name="测试任务", exact=True).click()
    page.get_by_role("button", name="新建任务", exact=True).click()
    page.locator("#taskName").fill("订单冒烟测试")
    page.locator("#taskDescription").fill("验证订单核心流程")
    page.locator('[data-editor-node="file:test_demo.py"] > summary').click()
    page.get_by_role("checkbox", name="选择用例 test_demo.py::test_ok", exact=True).check()
    page.locator(".execution-options summary").click()
    page.locator("#taskReport").uncheck()
    page.get_by_role("button", name="保存任务", exact=True).click()
    expect(page.locator("#taskItems")).to_contain_text("用例有效", timeout=15000)


@pytest.mark.integration
def test_task_to_report_browser_flow(workbench):
    from playwright.sync_api import expect

    page, manager, errors, tmp_path = workbench
    save_smoke_task(page)
    expect(page.locator("#sidebarShell")).to_be_visible()
    expect(page.locator(".main-header")).to_be_visible()
    assert page.locator("body").evaluate("node => getComputedStyle(node).backgroundColor") == "rgb(30, 30, 46)"
    assert page.locator("#sidebarShell").bounding_box()["x"] == 0
    page.screenshot(path=str(tmp_path / "tasks.png"), full_page=True)
    page.get_by_role("button", name="编辑", exact=True).click()
    page.locator("#taskDescription").fill("已更新的执行说明")
    page.get_by_role("button", name="保存任务", exact=True).click()
    expect(page.locator("#taskItems")).to_contain_text("已更新的执行说明")
    page.locator("input[name=verbosity][value=verbose]").check()
    page.get_by_role("button", name="运行任务", exact=True).click()
    expect(page.locator("#runStatus")).to_contain_text("通过", timeout=20000)
    page.get_by_role("button", name="用例结果", exact=True).click()
    expect(page.locator("#runOverview .metric.passed strong")).to_have_text("1")
    expect(page.locator("#runResults")).to_contain_text("test_ok")
    page.get_by_role("button", name="执行日志", exact=True).click()
    expect(page.locator("#historyLogViewport")).to_contain_text("browser test log")
    page.screenshot(path=str(tmp_path / "logs.png"), full_page=True)
    page.reload()
    expect(page.locator("#runTitle")).to_have_text("订单冒烟测试", timeout=10000)
    page.get_by_role("button", name="历史记录", exact=True).click()
    expect(page.locator("#historyList")).to_contain_text("订单冒烟测试")
    page.screenshot(path=str(tmp_path / "history.png"), full_page=True)
    page.get_by_role("button", name="查看详情", exact=True).click()
    expect(page.locator("#runResults")).to_contain_text("test_ok")
    page.get_by_role("button", name="测试任务", exact=True).click()
    page.get_by_role("button", name="编辑", exact=True).click()
    if not page.locator("#taskReport").is_visible():
        page.locator(".execution-options summary").click()
    page.locator("#taskReport").check()
    page.get_by_role("button", name="保存任务", exact=True).click()
    page.get_by_role("button", name="运行任务", exact=True).click()
    expect(page.locator("#runReportBtn")).to_be_visible(timeout=20000)
    with page.expect_popup() as popup:
        page.locator("#runReportBtn").click()
    report = popup.value
    expect(report.locator("body")).to_contain_text("test_ok")
    report.close()
    assert page.evaluate(
        """() => {const ids=[...document.querySelectorAll('[id]')].map(n=>n.id);return ids.length===new Set(ids).size;}"""
    )
    assert not errors, errors


@pytest.mark.integration
def test_deleted_or_renamed_case_has_visible_repair_flow(workbench):
    from playwright.sync_api import expect

    page, manager, errors, tmp_path = workbench
    save_smoke_task(page)
    (tmp_path / "test_demo.py").write_text("def test_renamed():\n    pass\n")
    page.get_by_role("button", name="重新检查用例", exact=True).click()
    expect(page.locator("#taskItems")).to_contain_text("需要修复", timeout=15000)
    page.get_by_role("button", name="修复用例", exact=True).click()
    expect(page.locator("#missingWarning")).to_be_visible(timeout=15000)
    expect(page.locator("#saveTask")).to_be_disabled()
    page.screenshot(path=str(tmp_path / "repair.png"), full_page=True)
    expect(page.locator("#editorCount")).to_have_text("已勾选 0 条用例")
    page.locator('[data-editor-node="file:test_demo.py"] > summary').click()
    page.get_by_role("checkbox", name="选择用例 test_demo.py::test_renamed", exact=True).check()
    expect(page.locator("#editorCount")).to_have_text("已勾选 1 条用例")
    page.get_by_role("button", name="保存任务", exact=True).click()
    expect(page.locator("#taskItems")).to_contain_text("用例有效", timeout=15000)
    task = manager.store.tasks()["items"][0]
    assert task["selection"]["nodeids"] == ["test_demo.py::test_renamed"]
    (tmp_path / "test_demo.py").write_text("syntax error !")
    page.get_by_role("button", name="重新检查用例", exact=True).click()
    expect(page.locator("#taskItems")).to_contain_text("未能校验", timeout=15000)
    expect(page.locator("#taskItems")).not_to_contain_text("需要修复")
    assert page.evaluate(
        """() => {const ids=[...document.querySelectorAll('[id]')].map(n=>n.id);return ids.length===new Set(ids).size;}"""
    )
    assert not errors, errors


@pytest.mark.integration
def test_monitoring_does_not_steal_navigation(workbench):
    from playwright.sync_api import expect

    page, manager, errors, tmp_path = workbench
    save_smoke_task(page)
    (tmp_path / "test_demo.py").write_text("import time\ndef test_ok():\n    time.sleep(5)\n")
    page.get_by_role("button", name="运行任务", exact=True).click()
    expect(page.locator("#runStatus")).to_contain_text("运行中", timeout=15000)
    page.get_by_role("button", name="测试任务", exact=True).click()
    expect(page.locator("#activeRunBanner")).to_contain_text("正在执行", timeout=6000)
    page.wait_for_timeout(3500)
    expect(page.locator("#viewTasks")).to_be_visible()
    expect(page.locator("#viewRun")).to_be_hidden()
    assert page.evaluate(
        """() => {const ids=[...document.querySelectorAll('[id]')].map(n=>n.id);return ids.length===new Set(ids).size;}"""
    )
    assert not errors, errors


@pytest.mark.integration
def test_large_log_tail_search_and_load_earlier(workbench):
    from playwright.sync_api import expect

    from lounger.web_runner.storage import now

    page, manager, errors, tmp_path = workbench
    rid = "a" * 32
    manager.store.create_run(
        dict(
            id=rid,
            state="completed",
            outcome="passed",
            started_at=now(),
            request={
                "selection": {"nodeids": ["test_demo.py::test_ok"]},
                "options": {"verbosity": "normal", "html_report": False},
            },
            result_status="unavailable",
        )
    )
    directory = manager.directory(rid)
    directory.mkdir(parents=True)
    content = "起始标记 START\n" + "中文日志内容 " * 5000 + "\n结束标记 END\n"
    (directory / "output.log").write_text(content, encoding="utf-8")
    page.get_by_role("button", name="历史记录", exact=True).click()
    page.get_by_role("button", name="查看详情", exact=True).click()
    page.get_by_role("button", name="执行日志", exact=True).click()
    expect(page.locator("#logRange")).to_contain_text("显示最近日志")
    page.locator("#logSearch").fill("END")
    expect(page.locator("#historyLogViewport")).to_contain_text("结束标记 END")
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.locator("#copyLog").click()
    expect(page.locator("#streamStatus")).to_have_text("已复制可见日志")
    expect(page.locator("#copyLog")).to_have_text("✓ 已复制")
    expect(page.locator("#copyFeedback")).to_be_visible()
    expect(page.locator("#copyFeedback")).to_have_text("已复制到剪贴板")
    assert page.evaluate("navigator.clipboard.readText()") == "结束标记 END"
    # A rejected Clipboard API must fall back to the browser's copy command.
    page.evaluate("navigator.clipboard.writeText('fallback sentinel')")
    page.evaluate("() => { navigator.clipboard.writeText = async () => { throw new Error('denied'); }; }")
    page.locator("#copyLog").click()
    expect(page.locator("#streamStatus")).to_have_text("已复制可见日志")
    expect(page.locator("#copyLog")).to_have_text("✓ 已复制")
    expect(page.locator("#copyFeedback")).to_be_visible()
    expect(page.locator("#copyFeedback")).to_have_text("已复制到剪贴板")
    assert page.evaluate("navigator.clipboard.readText()") == "结束标记 END"
    page.evaluate("document.execCommand = () => false")
    page.locator("#copyLog").click()
    expect(page.locator("#streamStatus")).to_contain_text("复制失败")
    expect(page.locator("#copyFeedback")).to_be_visible()
    expect(page.locator("#copyFeedback")).to_contain_text("复制失败")
    expect(page.locator("#copyLog")).to_have_text("复制可见日志")
    expect(page.locator("#copyLog")).to_be_enabled()
    page.locator("#earlierLogs").click()
    expect(page.locator("#earlierLogs")).to_be_hidden()
    page.locator("#logSearch").fill("START")
    expect(page.locator("#historyLogViewport")).to_contain_text("起始标记 START")
    response = page.request.get(page.locator("#downloadLog").evaluate("node => node.href"))
    assert response.text() == content
    assert not errors, errors


@pytest.mark.integration
def test_yaml_tree_expand_collapse_after_search_and_reload(workbench):
    from playwright.sync_api import expect

    page, manager, errors, tmp_path = workbench
    manager.collector = lambda root: [
        {"file": "datas/orders/test_create.yaml", "nodeid": "test_api.py::test_api[create]", "name": "创建订单"},
        {"file": "datas/users/test_user.yaml", "nodeid": "test_api.py::test_api[user]", "name": "读取用户"},
    ]
    page.get_by_role("button", name="刷新用例列表").click()
    directory = page.locator('[data-node-key="dir:datas"]')
    folder = page.locator('[data-node-key="dir:datas/orders"]')
    source = page.locator('[data-node-key="file:datas/orders/test_create.yaml"]')
    case = page.locator(".tree-case").filter(has_text="创建订单")
    expect(directory).to_be_visible()
    directory.click()
    folder.click()
    source.click()
    expect(case).to_be_visible()
    source.click()
    expect(case).to_be_hidden()
    source.click()
    folder.click()
    expect(source).to_be_hidden()
    folder.click()
    page.locator("#search").fill("创建订单")
    expect(case).to_be_visible()
    expect(page.locator('[data-node-key="dir:datas/users"]')).to_be_hidden()
    # Collapse still works with an active search, then clearing restores the saved state.
    source.click()
    expect(case).to_be_hidden()
    page.locator("#search").fill("")
    expect(case).to_be_hidden()
    source.click()
    expect(case).to_be_visible()
    directory.click()
    expect(folder).to_be_hidden()
    page.reload()
    expect(directory).to_be_visible()
    expect(folder).to_be_hidden()
    directory.click()
    expect(case).to_be_visible()
    assert not errors, errors


@pytest.mark.integration
def test_idle_has_no_project_polling_and_source_changes_refresh_tree(workbench):
    from playwright.sync_api import expect

    page, manager, errors, tmp_path = workbench
    expect(page.locator('[data-node-key="file:test_demo.py"]')).to_be_visible()
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    # Idle longer than two former polling intervals: the existing SSE stays open.
    page.wait_for_timeout(6500)
    assert not [url for url in requests if url.endswith("/api/v1/project")]
    assert not [url for url in requests if "/cases/" in url]
    (tmp_path / "test_demo.py").write_text("def test_renamed():\n    pass\n")
    page.locator("#search").fill("test_renamed")
    expect(page.locator(".tree-case").filter(has_text="test_renamed")).to_be_visible(timeout=15000)
    expect(page.locator(".tree-case").filter(has_text="test_ok")).to_have_count(0)
    assert not errors, errors


@pytest.mark.integration
def test_theme_switch_persists_without_changing_layout(workbench):
    from playwright.sync_api import expect

    page, manager, errors, tmp_path = workbench
    toggle = page.get_by_role("switch", name="夜间模式")
    expect(toggle).to_have_attribute("aria-checked", "true")
    sidebar_width = page.locator("#sidebarShell").bounding_box()["width"]
    toggle.click()
    expect(toggle).to_have_attribute("aria-checked", "false")
    assert page.locator("body").evaluate("node => getComputedStyle(node).backgroundColor") == "rgb(245, 246, 250)"
    save_smoke_task(page)
    page.screenshot(path=str(tmp_path / "theme-light.png"), full_page=True)
    page.get_by_role("button", name="编辑", exact=True).click()
    expect(page.locator("#saveTask")).to_be_enabled()
    page.screenshot(path=str(tmp_path / "theme-light-editor.png"), full_page=True)
    page.locator("#cancelTask").click()
    page.reload()
    expect(toggle).to_have_attribute("aria-checked", "false")
    assert page.locator("#sidebarShell").bounding_box()["width"] == sidebar_width
    toggle.focus()
    page.keyboard.press("Space")
    expect(toggle).to_have_attribute("aria-checked", "true")
    assert page.locator("body").evaluate("node => getComputedStyle(node).backgroundColor") == "rgb(30, 30, 46)"
    page.screenshot(path=str(tmp_path / "theme-dark.png"), full_page=True)
    page.reload()
    expect(toggle).to_have_attribute("aria-checked", "true")
    assert not errors, errors


@pytest.mark.integration
def test_task_run_defaults_to_quiet_and_honors_toolbar(workbench):
    from playwright.sync_api import expect

    page, manager, errors, tmp_path = workbench
    save_smoke_task(page)
    expect(page.locator("input[name=verbosity][value=quiet]")).to_be_checked()
    task = manager.store.tasks()["items"][0]
    manager.store.save_task({**task, "options": {**task["options"], "verbosity": "full"}}, task["id"])
    page.get_by_role("button", name="运行任务", exact=True).click()
    expect(page.locator("#runStatus")).to_contain_text("通过", timeout=20000)
    run = manager.store.runs()["items"][0]
    assert run["request"]["options"]["verbosity"] == "quiet"
    assert "browser test log" not in (manager.directory(run["id"]) / "output.log").read_text()
    assert not errors, errors


@pytest.mark.integration
@pytest.mark.parametrize("verbosity", ["quiet", "verbose"])
def test_log_arrives_before_execution_finishes_without_file_watcher(workbench, verbosity):
    import re

    from playwright.sync_api import expect

    page, manager, errors, tmp_path = workbench
    # Real-time output must not depend on native filesystem notification timing.
    manager.watcher.close()
    manager.watcher = None
    gate = tmp_path / "continue.txt"
    setup = "import time\nfrom pathlib import Path\n"
    wait = "    deadline=time.monotonic()+25\n    while not Path('continue.txt').exists() and time.monotonic()<deadline:\n        time.sleep(0.05)\n"
    if verbosity == "quiet":
        source = setup + 'def test_first():\n    print("HIDDEN_SUCCESS_DETAIL")\n\ndef test_second():\n' + wait
        count = "2"
    else:
        source = setup + 'def test_ok():\n    print("EARLY_OUTPUT_WITHOUT_NEWLINE", end="", flush=True)\n' + wait
        count = "1"
    (tmp_path / "test_demo.py").write_text(source)
    page.get_by_role("button", name="刷新用例列表").click()
    expect(page.locator("#caseStats")).to_contain_text("共 " + count + " 用例")
    page.locator(f"input[name=verbosity][value={verbosity}]").check()
    try:
        page.locator("#runAllBtn").click()
        if verbosity == "quiet":
            expect(page.locator("#historyLogViewport .log-line").filter(has_text=re.compile(r"^\.$"))).to_be_visible(
                timeout=10000
            )
            expect(page.locator("#historyLogViewport")).not_to_contain_text("HIDDEN_SUCCESS_DETAIL")
        else:
            expect(page.locator("#historyLogViewport")).to_contain_text("EARLY_OUTPUT_WITHOUT_NEWLINE", timeout=10000)
        assert manager.active_id is not None
        assert manager.store.run(manager.active_id)["state"] == "running"
    finally:
        gate.touch()
    expect(page.locator("#runStatus")).to_contain_text("通过", timeout=15000)
    assert not errors, errors


@pytest.mark.integration
def test_task_editor_yaml_hierarchy_counts_and_saved_selection(workbench):
    from playwright.sync_api import expect

    from lounger.web_runner.manager import validate_definition

    page, manager, errors, tmp_path = workbench
    ids = ["test_api.py::test_api[first]", "test_api.py::test_api[second]", "test_api.py::test_api[renamed]"]
    manager.collector = lambda root: [
        {"file": "datas/orders/test_order.yaml", "nodeid": nodeid, "name": name}
        for nodeid, name in zip(ids, ["创建订单", "查询订单", "已改名用例"])
    ]
    task = manager.store.save_task(
        validate_definition(
            {
                "name": "YAML 订单任务",
                "selection": {"nodeids": ids[:2] + ["test_api.py::test_api[old]"]},
            },
            task=True,
        )
    )
    page.get_by_role("button", name="测试任务", exact=True).click()
    page.get_by_role("button", name="编辑", exact=True).click()
    expect(page.locator("#editorCount")).to_have_text("已勾选 2 条用例")
    expect(page.locator("#missingWarning")).to_contain_text("1 条原用例")
    expect(page.locator("#selectedCasesList")).to_have_count(0)
    expect(page.locator("#casePickerList details[open]")).to_have_count(0)
    expect(page.locator('[data-editor-node="file:test_api.py"]')).to_have_count(0)
    for key in ["dir:datas", "dir:datas/orders", "file:datas/orders/test_order.yaml"]:
        page.locator(f'[data-editor-node="{key}"] > summary').click()
    first = page.get_by_role("checkbox", name="选择用例 " + ids[0], exact=True)
    expect(first).to_be_checked()
    expect(page.get_by_role("checkbox", name="选择用例 " + ids[1], exact=True)).to_be_checked()
    expect(page.get_by_role("checkbox", name="选择用例 " + ids[2], exact=True)).not_to_be_checked()
    directory = page.get_by_role("checkbox", name="选择目录 datas", exact=True)
    assert directory.evaluate("node => node.indeterminate")
    directory.check()
    expect(page.locator("#editorCount")).to_have_text("已勾选 3 条用例")
    first.uncheck()
    expect(page.locator("#editorCount")).to_have_text("已勾选 2 条用例")
    assert directory.evaluate("node => node.indeterminate")
    page.screenshot(path=str(tmp_path / "editor-yaml-tree.png"), full_page=True)
    page.locator("#cancelTask").click()
    assert manager.store.task(task["id"])["selection"]["nodeids"][-1].endswith("[old]")
    page.get_by_role("button", name="编辑", exact=True).click()
    expect(page.locator("#editorCount")).to_have_text("已勾选 2 条用例")
    expect(page.locator("#casePickerList details[open]")).to_have_count(0)
    page.locator("#saveTask").click()
    expect(page.locator("#taskDialog")).not_to_be_visible()
    assert manager.store.task(task["id"])["selection"]["nodeids"] == ids[:2]
    assert not errors, errors


@pytest.mark.integration
def test_history_delete_confirmation_and_last_page(workbench):
    from playwright.sync_api import expect

    from lounger.web_runner.storage import now

    page, manager, errors, _ = workbench
    save_smoke_task(page)
    task = manager.store.tasks()["items"][0]
    for index in range(21):
        manager.store.create_run(
            dict(
                id=f"{index:032x}",
                task_id=task["id"],
                task_name_snapshot=task["name"],
                state="running" if index == 20 else "completed",
                outcome=None if index == 20 else "passed",
                started_at=now(),
                request={
                    "selection": {"nodeids": ["test_demo.py::test_ok"]},
                    "options": {"verbosity": "quiet", "html_report": False},
                },
            )
        )
    rid = "0" * 32
    directory = manager.directory(rid)
    directory.mkdir(parents=True)
    (directory / "output.log").write_text("execution log")
    (directory / "report.html").write_text("report")
    page.get_by_role("button", name="历史记录", exact=True).click()
    active = page.locator(f'#historyList tr[data-run-id="{20:032x}"]')
    expect(active.get_by_role("button", name="删除", exact=True)).to_be_disabled()
    page.locator("#runPager").get_by_role("button", name="下一页").click()
    row = page.locator(f'#historyList tr[data-run-id="{rid}"]')
    expect(row.get_by_role("button", name="查看详情")).to_be_visible()
    row.get_by_role("button", name="删除", exact=True).click()
    page.locator(".confirm-dialog").get_by_role("button", name="取消", exact=True).click()
    expect(row).to_be_visible()
    assert directory.exists()
    assert manager.store.runs()["total"] == 21
    row.get_by_role("button", name="删除", exact=True).click()
    page.locator(".confirm-dialog").get_by_role("button", name="确认删除").click()
    expect(page.locator("#runPager")).to_contain_text("共 20 条 · 1 / 1 页")
    expect(row).to_have_count(0)
    assert not directory.exists()
    assert manager.store.runs()["total"] == 20
    assert manager.store.tasks()["items"][0]["id"] == task["id"]
    assert not errors, errors
