# Lounger 扩展点：plugin_hooks

> 对应 `docs/development_plan.md` §3.12（执行链 / 用例级 hook 化）。
> 业务侧需求（请求前后加逻辑、失败附加动作、用例级通知）走正式扩展点，
> **不要再 monkey patch `lounger.case.execute_step`**。

## 一、可用扩展点

| Hook | 触发时机 | 签名 |
|---|---|---|
| `register_before_execute_step` | 每个 YAML step 发请求**之前** | `func(case_step: dict) -> None` |
| `register_after_execute_step` | 每个 step 请求**成功返回后** | `func(case_step: dict, resp) -> None` |
| `register_on_execute_step_error` | step 抛异常时（异常会继续上抛） | `func(case_step: dict, exc: Exception) -> None` |
| `register_after_case_finish` | 每个 pytest 用例结束、**报告生成前** | `func(result: TestRunResult) -> None` |
| `register_after_run_finish` | 整个 run 结束（含报告路径） | `func(report_path, summary: TestRunSummary) -> None` |
| `register_after_session_finish` | pytest session 结束 | `func(summary: TestRunSummary) -> None` |

`TestRunResult` 字段：`nodeid` / `status`（passed|failed|skipped）/ `duration` / `description`。

## 二、注册方式

注册顺序 = 调用顺序。函数式注册与装饰器均可：

```python
# conftest.py
from lounger.log import log
from lounger.plugin_hooks import (
    register_after_case_finish,
    register_after_execute_step,
    register_before_execute_step,
    register_on_execute_step_error,
)


@register_before_execute_step
def log_request_start(case_step):
    log.info(f"▶ {case_step.get('name')} — before request")


@register_after_execute_step
def log_request_end(case_step, resp):
    log.info(f"✓ {case_step.get('name')} — {getattr(resp, 'status_code', '?')}")


@register_on_execute_step_error
def notify_step_error(case_step, exc):
    log.error(f"✗ {case_step.get('name')} — {exc}")  # 可在此发钉钉等


@register_after_case_finish
def notify_case_finish(result):
    # result: TestRunResult(nodeid, status, duration, description)
    log.info(f"📦 {result.nodeid} → {result.status} ({result.duration}s)")
```

## 三、优先级与共存规则

- **注册顺序即调用顺序**（同一 hook 多个注册者按注册先后执行）。
- 执行链 hook 与业务 `conftest.py` 中自定义的 **pytest hook**（如
  `pytest_runtest_makereport`、`pytest_sessionfinish`）互不影响：
  pytest 会执行所有 hookimpl，lounger 插件与业务 conftest 天然并存。
- `after_case_finish` 在 `pytest_runtest_makereport` 的 call 阶段触发，
  **早于 HTML 报告写入**，因此可在 hook 内做失败附加动作/通知。
- 一个用例只会触发一次 `after_case_finish`（setup 阶段失败/跳过的用例也会触发）。

## 四、迁移指南（从 monkey patch 迁移）

旧写法（不推荐）：

```python
# conftest.py — 直接替换框架函数
import lounger.case

_original = lounger.case.execute_step

def patched(case_step):
    do_something_before(case_step)
    _original(case_step)
    do_something_after(case_step)

lounger.case.execute_step = patched
```

新写法（推荐）：

```python
from lounger.plugin_hooks import register_before_execute_step, register_after_execute_step

@register_before_execute_step
def do_before(case_step):
    ...

@register_after_execute_step
def do_after(case_step, resp):
    ...
```

`lounger.case.execute_step` 的签名与行为保持不变，旧调用方无需改动。
