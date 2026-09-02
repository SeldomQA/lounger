# `--run-json` 执行协议

> 对应 `docs/development_plan.md` §3.7：`--run-json` 执行协议补文档 + 单测。

## 用途

平台化运行：外部系统（测试平台）先收集用例、按需组装执行顺序，再交给 pytest 按该顺序执行。

入口：`lounger.plugin.pytest_collection_modifyitems` 读取 `--run-json <file>` 指定的 JSON 文件，**按 JSON 中的顺序**重排 pytest 的执行队列。

## JSON 文件格式

```json
[
  { "nodeid": "test_api.py::test_api[test_assert::case_1_step_1]" },
  { "nodeid": "test_api.py::test_api[test_sample::case_1_step_1]" }
]
```

- 顶层为数组，每项至少包含 `nodeid`（测试用例唯一标识）。
- `nodeid` 必须是 pytest 收集到的真实用例 ID（可通过 `pytest --collect-only -q` 获取）。

## 执行语义

1. **按序执行**：`items[:] = selected_items`，pytest 队列被替换为 JSON 中列出的用例（顺序即 JSON 顺序）。
2. **缺失用例告警**：JSON 中出现的 `nodeid` 若未被 pytest 收集到，跳过该条并打印警告：
   ```
   WARNING No example was found, skipping execution: <nodeid>
   ```
   不会报错中断，其余用例照常执行。
3. **文件不存在**：`pytest.exit(f"JSON file not found: {json_path}")` —— 直接终止整个会话（非零退出码）。
4. **解析失败**（非法 JSON / 结构不符）：`pytest.exit(f"JSON parsing failed: {e}")` —— 同样终止会话。

## 示例

```bash
# 1. 收集用例到 JSON
pytest --collect-only -q | grep '::' > /dev/null  # 或使用 lounger.utils.collect

# 2. 组装执行顺序文件 run.json（由平台生成）

# 3. 按序执行
pytest --run-json run.json --junit-xml=reports/result.xml
```

参考实现：`myapi/platform_running.py`（`collected_cases` → `running_cases`）。

## 平台 API（F1，见 `docs/development_plan.md` §F1）

### 用例收集元数据

`lounger.utils.collect` / `lounger.services.case_discovery` 收集的每个用例输出额外字段：

```json
{
  "nodeid": "test_api.py::test_api[...]",
  "description": "...",
  "author": "tom",
  "priority": "P1",
  "tags": ["smoke", "api"]
}
```

解析约定（写在测试函数的 docstring 中，每行一条）：

```python
def test_getting_resource(get):
    """
    Getting a resource

    author: demo
    priority: P1
    tags: smoke, api
    """
    ...
```

- `author`: 任意字符串；
- `priority`: `P0` ~ `P3`（大小写不敏感）；
- `tags`: 逗号 / 分号 / 空格分隔；docstring tags 会与自定义 pytest mark
  （除 `parametrize` / `skip` / `env` / `integration` 外的 mark）合并去重。

### 结果回传（`--result-callback` / `--result-file`）

执行结束后把运行摘要 + 逐用例结果回传给平台：

```bash
pytest --run-json run.json \
       --junit-xml=reports/result.xml \
       --result-file=reports/result.json \
       --result-callback=https://platform.example.com/api/runs
```

payload 结构：

```json
{
  "summary": {"total": 3, "passed": 2, "failed": 1, "errors": 0, "skipped": 0, "exitstatus": 1},
  "report_path": "reports/result.html",
  "results": [
    {"nodeid": "a::t1", "status": "passed", "duration": 0.1, "description": "..."}
  ]
}
```

- `--result-file`：写入 JSON 文件（平台可轮询读取）；
- `--result-callback`：POST JSON 到 URL（best-effort，失败仅记日志不影响退出码）；
- 两者可同时使用。

### 全流程示例

`myapi/platform_running.py`（收集 → 执行 → 回传）：

```bash
cd myapi
LOUNGER_RESULT_CALLBACK=https://platform.example.com/api/runs python platform_running.py
```

## 单测覆盖

`tests/test_plugin_robustness.py`：
- JSON 中列出的用例按序重排 items；
- 缺失用例告警不中断；
- 文件不存在 / JSON 非法时 `pytest.exit` 终止。

`tests/test_platform_api.py`（F1）：
- docstring 元数据解析（author / priority / tags）；
- 收集输出含平台字段；
- result payload 结构与文件写入；
- `--result-callback` 成功 / 失败不抛异常。
