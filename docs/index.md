# Lounger

Next generation automated testing framework.

- **YAML 用例引擎**：`datas/**/test_*.yaml` → `teststeps` 模型校验、模板替换、变量提取、断言
- **协议适配**：HTTP（`RequestClient` / `HttpRequest` + `@api`）与 WebSocket（centrifuge）
- **Web UI**：`lounger.web_runner`（收集 / 执行 / SSE 实时日志）
- **数据库**：MySQL / MSSQL / PostgreSQL / SQLite，SSH 隧道，pytest fixture 工厂
- **平台化**：`--run-json` 按序执行协议（见 [平台执行协议](run_json.md)）

## 快速开始

```bash
pip install -e ".[dev]"
lounger create demo_api      # 生成脚手架（见 README 演练）
cd demo_api
pytest
```

## 文档导航

| 文档 | 内容 |
|---|---|
| [业务项目指南](project_guide.md) | 三层边界、conftest 规范、settings、扩展方式 |
| [扩展点 (plugin_hooks)](plugin_hooks.md) | 执行链 / 用例级 hook 注册与共存规则 |
| [平台执行协议](run_json.md) | `--run-json` JSON 格式与执行语义 |
| [平台化执行](platform.md) | 用例收集 → 执行 → 回传 |
| [开发计划](development_plan.md) | 完成状态与路线图（P0/P1 已闭环） |

## 快速链接

- 仓库：[github.com/SeldomQA/lounger](https://github.com/SeldomQA/lounger)
- 脚手架示例：`lounger/project_temp/`（api / web）
- 平台化示例：`myapi/platform_running.py`
