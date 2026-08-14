# Lounger 开发文档（Development Guide & Roadmap）

> 版本：1.3.3（基于代码现状 `82b7cff` + 近期已修复项）
> 文档目标：统一团队对"现状、优化方向、新功能路线"的认知，作为后续迭代的开发依据。

---

## 目录

1. [项目现状盘点](#1-项目现状盘点)
2. [近期已完成的修复](#2-近期已完成的修复)
3. [优化 & 重构建议](#3-优化--重构建议)
4. [新功能开发路线图](#4-新功能开发路线图)
5. [开发规范与 CI](#5-开发规范与-ci)
6. [里程碑与优先级](#6-里程碑与优先级)

---

## 1. 项目现状盘点

### 1.1 架构分层

```
┌─────────────────────────────────────────────────────────┐
│  业务项目层 (myapi / myweb)                                │
│  config/config.yaml · datas/**/test_*.yaml · test_dir/   │
│  support/db.py · support/notify.py                       │
├─────────────────────────────────────────────────────────┤
│  Lounger 框架层                                          │
│  ├─ 用例引擎   analyze_cases · case · commons            │
│  │            (template_engine / extract / assert_result)│
│  ├─ 协议适配   request (HTTP) · centrifuge (WebSocket)    │
│  ├─ Web UI    po.py (Playwright 封装)                    │
│  ├─ 数据操作   db_operation (MySQL/MSSQL/PG/SQLite)       │
│  ├─ Web 运行器 web_runner (HTTP server + SSE + HTML UI)  │
│  ├─ 能力底座   settings · plugin_hooks · integrations     │
│  │            utils (cache/variables/collect) · testdata │
├─────────────────────────────────────────────────────────┤
│  pytest 插件层 (lounger.plugin · pytest-req · xhtml)      │
└─────────────────────────────────────────────────────────┘
```

### 1.2 模块清单

| 模块 | 职责 | 规模 |
|---|---|---|
| `lounger/plugin.py` | pytest 插件：报告标题/截图/参数化描述/`--run-json` 执行协议/会话钩子 | 225 行 |
| `lounger/po.py` | Playwright Locator 手动封装（Page Object） | 988 行 |
| `lounger/request/` | HTTP 客户端（`RequestClient` + `HttpRequest` + `Expect` 断言） | ~470 行 |
| `lounger/commons/` | YAML 用例引擎：模型校验、模板替换、变量提取、断言 | ~500 行 |
| `lounger/db_operation/` | 数据库操作 + Fabric SSH 隧道 + 资源管理层 | ~1000 行 |
| `lounger/web_runner/` | Web 测试运行器（收集/执行/SSE/HTML 前端） | ~1200 行 |
| `lounger/settings.py` | 统一配置访问（可插拔 source） | 146 行 |
| `lounger/plugin_hooks.py` | 会话结束后置钩子（通知/报告） | 93 行 |
| `lounger/integrations/` | 钉钉通知集成（飞书占位） | 78 行 |
| `lounger/centrifuge/` | WebSocket 客户端管理 | 281 行 |
| `lounger/testdata/` | 随机数据生成 | 662 行 |

### 1.3 质量现状（实测）

| 指标 | 数值 | 说明 |
|---|---|---|
| 全量单测 | 89 passed / 11 failed / 3 skipped / 12 errors | 剩余失败均为**环境性**（`--base-url`、CWD 配置、本地 MySQL、Playwright 浏览器） |
| 收集期崩溃 | 2 个文件 | `test_db_mssql.py` / `test_db_postgresdb.py` 顶层 import 可选驱动 |
| CI | 无 | `.github/workflows/` 不存在 |
| 依赖锁定 | `python-dateutil==2.8.2` 锁死 | 其余均有区间 |

---

## 2. 近期已完成的修复

| 问题 | 状态 |
|---|---|
| `plugin.py::pytest_collection_modifyitems` 破坏类方法参数化测试（bound method 丢 `self`） | ✅ 已修（`types.MethodType` 重绑定 + 函数类型守卫） |
| `po.py::element_handle` 参数笔误 `timeit` → `timeout` | ✅ 已修 |
| `po.py::input_value` 重复定义（async 覆盖 sync） | ✅ 已修（删除 async 副本） |
| `assert_result.py` 裸表达式未按 JMESPath 作用于 body | ✅ 已修（docstring 契约落地） |
| `request_client.py::_files_load` 文件句柄泄漏 | ✅ 已修（返回句柄 + 请求结束统一关闭） |
| 环境问题：venv 中旧安装快照 | ✅ 已切换 editable 安装 |

---

## 3. 优化 & 重构建议

按优先级分三档。**建议落地顺序：先 P0（让项目可跑、可验证），再 P1（架构收敛），P2 持续做。**

### 3.0 来源对照：thinking.md / steps.md 完成度

> `docs/thinking.md`（10 项架构收敛建议）与 `docs/steps.md`（按优先级拆分的落地步骤）是两份历史设计文档。
> 下表逐条核对当前代码现状：✅ 已完成 / 🟡 部分完成 / ❌ 未完成，未完成项已并入下文对应小节。

| 来源 | 条目 | 现状 | 跟踪位置 |
|---|---|---|---|
| thinking #3 / steps | 统一 settings 入口 | ✅ 完成（`lounger/settings.py`：Yaml/Dict source、`get/get_int/get_bool`） | — |
| thinking #4 / steps | ExtractVar 注册范围收窄 | 🟡 显式注册表 `LOUNGER_TEMPLATE_FUNCTIONS` + 仅本模块函数已做；`lounger.runtime.register_template_func` API、自动扫描弃用警告未做 | [3.6](#36-extractvar-注册机制收尾) |
| thinking #5 / steps | MySQL 资源层 | 🟡 `MySQLResource` / `SSHTunnelConfig` / `build_mysql_resource` 已做；`DatabaseFactory` 统一工厂、`create_mysql_fixture()` fixture 工厂未做 | [3.13](#313-数据库资源层收尾databasefactory--fixture-工厂)（新增） |
| thinking #6 / steps 步骤3 | 请求层双轨合并 | ❌ `RequestClient` 与 `HttpRequest + @api` 仍并行 | [3.5](#35-请求层双轨合并对齐-docsthinkingmd-第-6-条) |
| thinking #7 / steps 步骤1 | 通知 / 后处理 hook 化 | 🟡 主体完成（`plugin_hooks` + `integrations/dingtalk` + `pytest_sessionfinish` 触发 + 脚手架 `support/notify.py` 薄示例）；`after_case_finish` 用例级 hook、飞书落地、使用文档缺失 | [3.12](#312-执行链--用例级-hook-化) + 路线图 [F4](#f4-通知渠道扩展) |
| thinking #8 / steps 步骤2 | 执行链 hook 化（替代 monkey patch） | ❌ `case.py` 无任何 hook（`before_execute_step` / `after_execute_step` / `on_execute_step_error`） | [3.12](#312-执行链--用例级-hook-化)（新增，steps 第二优先级） |
| thinking #9 / steps 步骤4 | runner 与内核解耦（service 层） | ❌ 无 `lounger.services`，收集/执行/状态仍耦在 `web_runner` 目录 | [3.8](#38-web_runner-解耦与健壮性) + 路线图 [F1](#f1-平台化-api-完善) |
| thinking #10 | 官方推荐扩展方式文档 | ❌ 未成文（脚手架注释示例已示范，缺正式文档） | [P2 文档](#p2--质量与体验持续)（新增） |
| thinking #1 / #2 | 三层边界 + 薄 conftest | 🟡 脚手架已拆 `support/db.py` / `support/notify.py`；框架自带 `tests/conftest.py` 仍堆钉钉逻辑，且缺规范文档 | [3.1](#31-测试套件一键可跑最高优先级) + [P2 文档](#p2--质量与体验持续) |

**steps.md 中"业务侧旧 `pytest_sessionfinish` 兼容"**：pytest 会执行所有 hookimpl，业务 conftest 自定义的 `pytest_sessionfinish` 与 lounger 插件的天然并存，无需特殊处理（文档中说明即可）。


### P0 — 可运行性与工程化（1 周内）

#### 3.1 测试套件一键可跑（最高优先级）

**目标**：`pip install -e .[dev] && pytest tests/` 在干净环境必须全绿（单元级）。

| 问题 | 方案 |
|---|---|
| `test_db_mssql.py` / `test_db_postgresdb.py` 顶层 import 可选驱动 → **收集期崩溃** | 改为 `pymssql = pytest.importorskip("pymssql")`（在模块内，非 try/except）；驱动移入 `[project.optional-dependencies]` |
| `test_db_mysql.py` 硬编码 `root/198876` 连本地 MySQL | 加 `@pytest.mark.integration` + 无环境变量（如 `LOUNGER_TEST_MYSQL`）时 `skip` |
| `test_request.py` / `test_api_object.py` 依赖 `--base-url` | 标记 `integration`；conftest 中 `base_url` 为空时 `pytest.skip` |
| Playwright 用例（`test_playwright.py` 等）在无浏览器环境报错 | 浏览器由 CI 安装；`tests/pytest.ini` 的 `--headed` **移出 addopts** |
| `tests/conftest.py` 每次运行发钉钉 webhook（占位 URL，日志噪音） | 删除；或改为环境变量开关（`LOUNGER_NOTIFY` 存在才启用） |
| `test_config_var.py` 依赖 CWD 的 `config/config.yaml` | 配合 3.5 配置锚定项目根后自然消除 |

**约定**：`pytest tests/` = 单元级（默认）；`pytest -m integration` = 外部依赖级。

#### 3.2 建立 CI（`.github/workflows/ci.yml`）

草案见 [5.2 节](#52-ci-工作流草案)。

#### 3.3 仓库卫生

- `.gitignore` 补充：
  ```
  collected_cases/
  lounger/utils/cache_data.json
  tests/data/*.sqlite3
  reports/
  *.csv            # 根目录个人数据文件
  ```
- 移除已提交产物：`myapi/collected_cases/test_cases_info.json`（含绝对路径，换机器即失效）、`lounger/utils/cache_data.json`。
- 清理根目录误放的个人文件（`boss_resume_screening_*.csv`、`测试工程师简历筛选标准.md`）。
- 未跟踪的新代码（`docs/thinking.md`、`integrations/feishu.py`、新增测试）尽快决策入库。

### P1 — 架构收敛（2-4 周）

#### 3.4 配置系统收尾（settings 已建立，做三件事）

1. **锚定项目根**：`YamlSettingsSource` 从 CWD 向上查找 `config/config.yaml`，消除"换个目录配置就丢"的问题（当前 `test_config_var.py` 的根因）。
2. **消除 import 时求值**：`load_config.py:21` 的 `base_url = base_url()` 是模块级常量，`RequestClient` 单例在 import 时绑定 → 改配置必须重启进程。改为惰性读取：
   ```python
   # 方案：request_client 不再持有 import 时绑定的 Session
   def send_request(self, **kwargs):
       session = Session(settings.get("base_url"))   # 每次按最新配置
   ```
   或保留单例但暴露 `set_base_url()`。`base_url` 兼容层保留为属性（`@property`），不再做模块级常量。
3. **新增 `EnvConfigSource`**（环境变量覆盖 YAML），并给 `Settings.get` 加文件 mtime 缓存（当前每次全量解析 YAML）。
4. **淘汰 `ConfigUtils`**：现仅 `settings.py` 内部使用，标记 deprecated，下个大版本移除。

#### 3.5 请求层双轨合并（对齐 `docs/thinking.md` 第 6 条）

现状两套 API 并存：`RequestClient`（YAML 引擎用）与 `HttpRequest + @api`（代码式 API Object）。

- **目标**：`RequestClient` 为唯一主路径。
- 步骤：
  1. `HttpRequest` 改为内部复用 `RequestClient`（base_url、headers、日志统一）；
  2. `@api` 装饰器保留（生态兼容），但断言/提取复用 `assert_result` / `extract`；
  3. 统一 `Expect` 断言入口（`request/assertions.py` 已有，补 doc 示例）；
  4. 增加"同一请求两种写法"的一致性单测。

#### 3.6 ExtractVar 注册机制收尾

已实现：`LOUNGER_TEMPLATE_FUNCTIONS` 显式注册 + 仅加载 conftest 本模块函数。
- 继续：默认只读显式注册表；自动扫描降级为 fallback 并打 deprecation 警告；
- 模板函数注册点从 conftest 抽到 `lounger/runtime`（支持插件注册）；
- 与 `settings` 打通：`${config(x)}` / `${extract(x)}` 语义在文档中明确。

#### 3.7 plugin.py 健壮性

- `--html-title` / `--env` 的 `default=[]` 改为 `default=None`（语义正确）；
- `pytest_runtest_makereport` 中 `page` 截图逻辑抽为可测试函数；
- `--run-json` 执行协议（JSON 文件 → 按序执行 → 缺失用例告警）补文档 + 单测；
- `pytest_collection_modifyitems` 的 docstring 装饰逻辑已加固（bound method / 非函数守卫），补一个"装饰后 docstring 正确"的显式单测（目前仅靠 `test_params_class_data` 间接覆盖）。

#### 3.8 web_runner 解耦与健壮性

| 问题 | 方案 |
|---|---|
| `_active_runs` 无清理，长驻服务内存无限增长 | 完成即归档：内存保留最近 N 次（如 20），其余落盘 `reports/runs/` |
| `collect.py` 硬编码正则 `test_api\.py::test_api\[...\]` | 命名规则插件化：优先 YAML metadata 反查，无则 fallback 通用规则 |
| 收集/执行耦合在 web_runner 内 | 抽 `lounger/services/case_discovery.py` + `test_execution.py`，CLI/Web/平台共用 |
| `html.py` 将 `JSON.stringify` 结果拼进 `data-ids` 属性（含引号会破 HTML） | 改用 `encodeURIComponent` 或 `data-ids` + `dataset` |
| 收集子进程超时/异常仅有 stderr 打印 | 返回结构化错误（`{"error": ...}`）供前端展示 |

#### 3.9 po.py 手抄 API 漂移治理

988 行手抄 Playwright Locator 已出现 2 处漂移（`timeit`、`input_value` 重复）。短期：
- 为 `Locator` 的每个包装方法补"参数透传正确性"单测（dummy driver 断言 kwargs）；
长期方案二选一：
- **A（推荐）**：包装层只保留 lounger 扩展能力（日志/describe），其余方法直接透传 Playwright Locator（`__getattr__` 委托），从根上消除漂移；
- B：写脚本比对 `Locator` 与 playwright `Locator` 签名差异，纳入 CI。

#### 3.10 Cache 与并发语义

- 现状：临时目录单文件 JSON，无 TTL，跨用例共享，web_runner 子进程语义不明确。
- 方案：文件 + mtime 失效；键支持命名空间（`<project>:<key>`）；文档明确"缓存跨测试进程共享、测试间需 `cache.clear()`"的语义；
- `memory_cache` / `DiskCache` 已有，补 TTL 与并发单测。

#### 3.11 依赖与打包

```toml
[project.optional-dependencies]
dev = ["pytest", "ruff", "black", "playwright"]
db-mysql = ["PyMySQL>=1.1.1"]
db-mssql = ["pymssql>=2.2"]
db-postgres = ["psycopg2-binary>=2.9"]
ai = ["autowing>=0.7.0"]
```

- `python-dateutil==2.8.2` 放宽为 `>=2.8.2,<3`；
- 主依赖只保留核心（pytest 插件、yaml、click），DB/AI/Playwright 全部 extras——降低基础安装体积。

#### 3.12 执行链 / 用例级 hook 化

> **来源**：`docs/thinking.md` #7 收尾 + #8；`docs/steps.md` 步骤 1-2（第二优先级）。
> 现状：通知类 hook（session/run）已完成；**用例级 hook 完全缺失**——业务侧只能 monkey patch `lounger.case.execute_step`。

**目标**：业务侧需求（请求前后加逻辑、失败附加动作、用例级通知）走正式扩展点，不再改框架函数。

1. **`case.py::execute_step` 增加执行链 hook**（核心改动，对应 thinking #8）：
   ```python
   # lounger/case.py
   def execute_step(case_step):
       on_before_execute_step(case_step)          # 请求前
       try:
           resp = _dispatch(case_step)            # request / centrifuge
       except Exception as exc:
           on_execute_step_error(case_step, exc)  # 失败回调
           raise
       on_after_execute_step(case_step, resp)     # 请求后
       ...
   ```
   - hook 注册机制放 `plugin_hooks.py`（与 `register_after_session_finish` 同款）：`register_before_execute_step` / `register_after_execute_step` / `register_on_execute_step_error`；
   - hook 签名稳定后，提供 `execute_step` 的兼容包装，保证旧 monkey patch 用法不炸（文档给出迁移指南）。
2. **`after_case_finish(result)` 用例级通知 hook**（对应 thinking #7 的缺失项）：在 `pytest_runtest_makereport` 中触发，`TestRunResult` 含 `nodeid / status / duration / description`；供"失败后附加动作 / 用例级通知"使用。
3. **脚手架薄示例**：`project_temp/api` 中给一个"在请求前后打点 / 失败发通知"的注释示例，而不是把逻辑塞进 `conftest.py`。
4. **文档**：`plugin_hooks` 扩展点一节（注册方式 + 优先级 + 与业务 `conftest.py` hook 的共存规则）。

**验收**：`tests/test_execution_hooks.py` 覆盖三个执行链 hook 的调用时机与参数；`after_case_finish` 在报告生成前触发；脚手架示例可运行。

#### 3.13 数据库资源层收尾（DatabaseFactory / fixture 工厂）

> **来源**：`docs/thinking.md` #5。现状：`MySQLResource` / `build_mysql_resource` 已做（资源编排 + 隧道生命周期接管），
> 但"统一工厂 + pytest fixture 工厂"未落地，且 Postgres/MSSQL 仍各自为政（`postgres_db.py` / `mssql_db.py` 顶层 import 可选驱动）。

1. **`DatabaseFactory`**（`db_operation/factory.py`）：
   ```python
   db = DatabaseFactory.mysql(connection=MySQLConnectionConfig(...), tunnel=SSHTunnelConfig(...))
   db = DatabaseFactory.postgres(host=..., port=..., database=..., user=..., password=...)
   db = DatabaseFactory.mssql(server=..., user=..., password=..., database=...)
   ```
   - 统一返回"可 close / 可上下文管理"的连接对象；Postgres/MSSQL 复用同一资源模型（连接配置 + 可选隧道）。
2. **标准 pytest fixture 工厂**：
   ```python
   # lounger/db_operation/fixtures.py
   mysql_db = create_mysql_fixture(scope="session", config_source=ExtractVar().config)
   ```
   - 业务项目一行启用，无需手写连接/关闭/隧道逻辑。
3. **可选驱动 import 下沉**：`pymssql` / `psycopg2` 改为惰性 import（类方法内），顶层不再抛 `ModuleNotFoundError`——从根上消除 `test_db_mssql.py` / `test_db_postgresdb.py` 的收集期崩溃（与 3.1 联动）。

**验收**：`test_db_tunnel.py` 扩展覆盖 `DatabaseFactory` 三类连接；fixture 工厂单测（session 级复用、关闭幂等）；无驱动环境下 `import lounger.db_operation` 不报错。

### P2 — 质量与体验（持续）

- **类型标注**：核心模块（settings / plugin_hooks / request / commons）已部分标注，扩展到全量；`mypy --strict` 或 `pyright` 进 pre-commit。
- **代码风格**：`ruff` + `black` 配置进 `pyproject.toml`，`pre-commit` 钩子。
- **日志规范**：错误路径统一 `log.error` + 异常链；避免在热路径打印 INFO（如 `cache.get` 每次调用都 INFO）。
- **文档站**：`mkdocs` + `docs/` 现有内容整合（platform.md / steps.md / thinking.md / development_plan.md），补 API 参考（`pydoc-markdown`）。
- **脚手架示例质量**：`project_temp` 与 `myapi`/`myweb` 示例保持一致并附 README 演练。
- **官方推荐扩展方式文档（thinking #1/#2/#10）**：新增 `docs/project_guide.md`（业务项目开发指南），明确：
  - 三层边界（框架内核 / 项目配置层 / 业务扩展层）；
  - `conftest.py` 只允许放三类东西（fixture / pytest hook / 少量 helper 导入注册），并给出"推荐 / 不推荐"清单（直接采用 thinking.md #10 的表述）；
  - 配置统一走 `settings`（不再直接依赖 `config.yaml` 文件结构）；
  - 模板函数显式注册；执行链扩展走 hook（3.12），禁止 monkey patch 框架内核。

---

## 4. 新功能开发路线图

### 4.1 v1.4 — 近期（1-2 个月）：平台化与运行器

#### F1. 平台化 API 完善
- **背景**：`--run-json` 已支持"按 JSON 指定用例顺序执行"，`platform_running.py` 已有收集/执行雏形。
- **方案**：
  - 用例收集输出增加 `tags` / `author` / `priority` 字段（从 mark/docstring 解析）；
  - 提供结果回调：`--result-callback <url>` 或结果文件（junit + json），供平台入库；
  - `lounger.services.case_discovery` 统一收集逻辑（web_runner 与 CLI 复用）。
- **验收**：`python platform_running.py` 全流程（收集→执行→回传）在示例项目可用，附文档。

#### F2. 报告增强
- pytest-xhtml 定制：环境信息块（Python/浏览器/项目/时间）、用例耗时排序、失败截图聚合、YAML 用例展示 `step` 描述（已支持 description 列）。
- 报告文件路径默认 `reports/result_<ts>.html`，并写入 `TestRunSummary`。

#### F3. web runner v2
- 运行历史持久化（`reports/runs/`），支持查看历史日志/结果；
- 多 run 并发管理（当前全局单状态）；多项目切换（`--project` 已支持，补 UI 入口）；
- 用例标签筛选、收藏（localStorage 已有展开态持久化，扩展之）。

#### F4. 通知渠道扩展
- 落地 `integrations/feishu.py`（现有占位），企业微信、邮件作为后续；
- 通知内容模板化（失败详情 + 报告链接），`plugin_hooks` 已就绪。

### 4.2 v1.5 — 中期（3-5 个月）：AI 与数据驱动

#### F5. AI 测试能力深化
- **现状**：`autowing` 集成（`ai_action` / `ai_query`）在脚手架示例中可用。
- **方向**：
  - AI 断言：`expect(ai_query(...)).to_contain(...)`；
  - 元素定位自愈：用例失败时用 AI 重新匹配选择器并给出建议；
  - 自然语言用例：`test_ai_sample.py` 模式推广到 YAML（`ai: 描述` 步骤）。
- **验收**：YAML 用例支持 `ai` 步骤类型；自愈建议写入报告。

#### F6. 多环境支持
- `env` 标记已有（`@pytest.mark.env`），补：
  - 环境矩阵执行（`--env prod --env staging` 多轮）；
  - 环境相关配置（`config/<env>.yaml` 覆盖，配合 `EnvConfigSource`）；
  - 报告标注执行环境。
- **验收**：一套用例在 2 个环境跑完并各自出报告。

#### F7. 数据驱动增强
- 数据源扩展：数据库（SQL 查询结果作为参数）、Excel 多 sheet、CSV 表头映射（当前为纯列表）；
- 参数生成：组合（笛卡尔积）、依赖字段（如"注册→登录"数据链）；
- 大参数集分片（配合 xdist）。

#### F8. 用例编排
- `prescript` / `presteps` 已有，补：
  - 步骤级失败重试（与 `pytest-rerunfailures` 打通，仅重试"幂等步骤"）；
  - 用例依赖（`dependence.py` 目前仅函数级缓存，升级为用例级依赖声明 `@pytest.mark.depends`）；
  - 分组并行：按文件/标签分片执行（`pytest-xdist` 已有，补推荐分片策略文档）。

### 4.3 v2.0 — 长期（6 个月+）：生态

#### F9. 分布式执行与调度
- 执行队列服务：`lounger.services.scheduler`（本地队列 → 后续对接 CI 或消息队列）；
- 跨机器报告聚合（junit + json 合并）。

#### F10. 插件生态
- 前置：执行链 / 用例级 hook（见 [3.12](#312-执行链--用例级-hook-化)）在 P1 阶段落地后，本项聚焦"生态化"：
  - 把 `plugin_hooks` 全部扩展点（session / run / case / 执行链）整理成官方插件开发指南（含优先级与共存规则）；
  - 官方插件示例（通知、上传报告、CI 集成）；
  - 插件发现机制（`lounger.plugins` entry point）。

#### F11. 测试资产中心
- 元素库（PO 选择器共享）、接口定义（OpenAPI 导入生成请求模板）、数据工厂（`testdata` 扩展为工厂模式）。

#### F12. IDE / CI 集成
- 提供 `lounger` GitHub Action（install → 配置 → run → upload report）；
- VS Code 扩展（用例树浏览、单用例执行）基于 `lounger.services`。

---

## 5. 开发规范与 CI

### 5.1 开发规范

| 项 | 约定 |
|---|---|
| 分支模型 | `main` 稳定分支；功能分支 `feat/xxx`，修复分支 `fix/xxx`；PR 合入 |
| 提交信息 | 沿用现有风格：`feat:` / `fix:` / `test:` / `docs:` / `refactor:` / `chore:` + 简短中文或英文描述 |
| 单测要求 | **每个 bug 修复必须带回归单测**；新功能必须带单测；合入前 `pytest tests/`（单元级）全绿 |
| 代码风格 | `ruff` + `black`；`pyproject.toml` 中配置并进 pre-commit |
| 依赖 | 新增依赖必须进 `pyproject.toml`（按 extras 归类），不得隐式依赖 |
| 文档 | 公共 API 必须有 docstring（含参数/返回/示例）；用户可见功能更新 README 或 docs |

### 5.2 CI 工作流草案

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  unit:
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ matrix.python-version }}" }
      - run: pip install -e ".[dev]"
      - run: ruff check lounger tests
      - run: pytest tests/ -m "not integration" -q

  web:
    needs: unit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
      - run: playwright install --with-deps chromium
      - run: pytest tests/test_playwright.py tests/test_page_object.py -q --browser=chromium
```

> 注：`tests/pytest.ini` 中 `--headed` 需先移出（见 3.1），否则 CI 会打开真实浏览器窗口。

---

## 6. 里程碑与优先级

| 阶段 | 内容 | 预估 | 依赖 |
|---|---|---|---|
| **P0-1** | 测试套件可运行 + CI 建立 + 仓库卫生 | 1 周 | 无 |
| **P1-1** | 配置锚定项目根 + `base_url` 惰性化 | 3-5 天 | P0-1 |
| **P1-2** | 请求层合并 + ExtractVar 收尾 | 1 周 | P1-1 |
| **P1-3** | web_runner 解耦 + 状态清理 + 收集规则插件化 | 1-2 周 | P1-1 |
| **P1-4** | po.py 透传化 + 签名对齐测试 | 1 周 | 无 |
| **P1-5** | 执行链 / 用例级 hook 化（thinking #7/#8、steps 步骤 1-2） | 1 周 | P0-1 |
| **P1-6** | 数据库资源层收尾（DatabaseFactory + fixture 工厂 + 可选驱动惰性 import） | 1 周 | P1-1 |
| **P1-7** | 官方推荐扩展方式文档（`docs/project_guide.md`） | 2-3 天 | P1-5 |
| **V1.4** | F1-F4（平台化 API / 报告 / runner v2 / 通知含飞书） | 1-2 个月 | P1-1 ~ P1-3 |
| **V1.5** | F5-F8（AI / 多环境 / 数据驱动 / 编排） | 3-5 个月 | V1.4 |
| **V2.0** | F9-F12（分布式 / 插件生态 / 资产中心 / IDE 集成） | 6 个月+ | V1.5 |

**建议立即启动的三件事**（性价比最高）：
1. 测试套件可运行性（P0-1）——让每个 PR 都有可靠的验证基线；
2. 配置锚定项目根 + `base_url` 惰性化（P1-1）——消除最常见的使用困惑；
3. 执行链 / 用例级 hook 化（P1-5）——`docs/steps.md` 明确的第二优先级，改动集中在 `case.py` + `plugin_hooks.py`，可独立交付，业务侧从此不用 monkey patch 框架。
4. 请求层双轨合并（P1-2）——降低后续所有请求相关功能的维护成本。
