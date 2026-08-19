## 1.5.1(2026-08-19)

本版本主要**修复 CI 兼容性问题**（pytest-playwright 0.8.0、loguru 日志），并更正一项历史设计决策（`ConfigUtils` 保留为公开 API，不废弃）。

### 修复 Bug

* 修复：pytest-playwright `>=0.8.0` 与内层 pytest 会话冲突。
* 修复：loguru 日志报 `I/O operation on closed file`。
* 修复：`webhook.py` mypy 构建错误（`json` 参数与 `JsonType` 类型不兼容）——抽出 `_text_payload` / `_markdown_payload`，显式 `dict[str, Any]` 返回类型。
* 修复：`request_client.py` 在 `json=None` 时误加 `Content-Type`、误进 GraphQL 分支——改为 `kwargs.get("json") is not None` 判断。

### 变更与更正

* `ConfigUtils` 保留为公开 API，**不废弃**（更正此前"淘汰 ConfigUtils"的历史决策）。
* `HttpRequest` 收敛到 `RequestClient`：去除对 `pytest_req` 的 `request` 装饰器依赖，内部统一走 `RequestClient.
* `config_utils.py` 增强：多文件分层加载 + 深合并（URL 简写、同名字段覆盖）+ mtime 文件缓存。

## 1.5.0(2026-08-16)

本版本为一次**修复 bug + 重构优化 + 更正历史设计错误**的发布，同时补齐 P0/P1/P2 开发计划（详见 `docs/development_plan.md`）。

### 修复 Bug

* 修复：`po.py` 手抄 Playwright API 漂移。
    * 修复：`dispatch_event` 参数名错误（`eventInit` → `event_init`），调用时传参会抛 `TypeError`。
    * 修复：`timeit` 参数笔误、`input_value` 重复定义（历史遗留）。
    * 新增 `Locator.__getattr__` 透传未手抄的 Playwright 方法，从根上消除"遗漏方法"类漂移。
* 修复：`load_config.py` 冗余的 `def base_url()` 定义导致 ruff F811、CI 失败。
* 修复：web_runner 启动信息用 `print` 输出 emoji，在 GBK 控制台（Windows 默认）直接崩溃——改用 loguru。
* 修复：web_runner `main()` 设置的 `_scan_dir` 不生效（`--project` 参数无效），统一走 `state` 模块访问。
* 修复：`html.py` 将 `JSON.stringify` 结果拼进 `data-ids` 属性，含引号的 nodeid 会破坏 HTML——改用 `encodeURIComponent`。
* 修复：`.gitignore` 中文注释为 GBK 编码，导致 black 等按 UTF-8 读取的工具崩溃。

### 重构与优化

* 配置系统收尾（settings 统一入口）。
    * `YamlSettingsSource` 项目根锚定：从 CWD 向上查找 `config/config.yaml`，换目录执行不再丢配置。
    * 文件 mtime 缓存：编辑配置无需重启进程，下次 `get()` 自动生效。
    * 新增 `EnvConfigSource`：`LOUNGER_*` 环境变量覆盖 YAML。
    * `base_url` 改为惰性代理，兼容 `base_url()` 调用与 `f"{base_url}"` 值用法两种历史形态。
* 请求层双轨合并：`HttpRequest` 委托 `RequestClient`（唯一主路径），`@api` 断言/提取复用 `assert_result` 表达式（`status_code` / `body.<jmespath>` / 裸 JMESPath）。
* 执行链 hook 化：`case.py::execute_step` 增加 `before/after/error` 三个执行链 hook，业务侧从此不用 monkey patch 框架。
* web_runner 解耦：抽取 `lounger.services.case_discovery` / `test_execution`，CLI/Web/平台共用；运行历史归档落盘 `reports/runs/`，内存有界。
* 收集子进程异常返回结构化 `{"error": ...}`，供前端展示。
* Cache 语义完善：TTL 惰性过期、`<namespace>:<key>` 命名空间、热路径日志降级（`get` INFO→DEBUG）。
* 全量类型标注：`mypy` 通过（80 源文件），`[tool.mypy]` / `ruff` / `black` 配置进 `pyproject.toml`，pre-commit 钩子（ruff + black + mypy）与 CI 集成。

### 更正之前的错误设计

* 依赖收敛：主依赖只保留核心（pytest 插件、yaml、click、openpyxl 等）；DB/AI/Playwright 全部下沉到 extras（`db-mysql` / `db-mssql` / `db-postgres` / `db-ssh` / `ai` / `dev`）。
* 可选驱动惰性导入：`pymysql` / `pymssql` / `psycopg2` 顶层不再抛 `ModuleNotFoundError`，无驱动环境可正常 `import lounger`。
* `ConfigUtils` 标记弃用（DeprecationWarning），统一走 `lounger.settings`。
* `--html-title` / `--env` 的 `default=[]` 改为 `default=None`（语义正确）。
* ExtractVar 自动扫描弃用：模板函数显式注册（`lounger.runtime.register_template_func` / `LOUNGER_TEMPLATE_FUNCTIONS`）。

### 文档

* 新增 `docs/project_guide.md`（业务项目开发指南）、`docs/plugin_hooks.md`（扩展点）、`docs/run_json.md`（平台执行协议）。
* 新增 mkdocs 文档站（`mkdocs.yml` + `docs/index.md`）。
* 脚手架 `project_temp/api` 增加 README 演练。

## 1.3.3(2026-06-30)

* 功能：统一配置入口 `lounger.settings`（Yaml/Dict source、`get/get_int/get_bool`）。
* 功能：数据库资源管理层（`MySQLResource` / `SSHTunnelConfig` / `build_mysql_resource`）。
* 功能：`DatabaseFactory` + fixture 工厂（`create_mysql_fixture` 等 4 个）。
* 功能：plugin hooks 机制（`register_after_session_finish` / `register_after_run_finish`）。
* 功能：模板函数显式注册（`lounger.runtime.register_template_func`）。
* 功能：请求断言统一入口 `expect`（`to_have_path_*` 系列）。
* 修复：参数化测试类方法丢 `self`（`pytest_collection_modifyitems` bound method 重绑定）。
* 修复：`_files_load` 文件句柄泄漏。
* 修复：`save_response` 保存响应。

## 1.3.2(2026-05-22)

* lounger测试运行器优化。
    * 功能：增加`复制日志`按钮，一键复制运行日志。
    * 功能：增加日志模式`静默/标准/详细/完整`。
    * 功能：被运行过的用例做颜色区分，方便用例过时查看。
    * 修复：`BrokenPipeError` 异常处理

## 1.3.1(2026-05-15)

* lounger测试运行器重构。
    * 变更：使用新的启动命令：`lounger runner --port 5002`
    * 功能：测试文件增加测试按钮，支持测试文件执行。
    * 修复：搜索之后再运行，搜索状态丢失问题。
    * 修复：默认使用`0.0.0.0`导致Windows启动失败。
    * 重构：对整个实现代码重构，方便后续维护。

## 1.3.0(2026-05-11)

* 增加`lounger-runner`命令，方便的执行用例。🎉
* SQL操作减少冗余的日志。

## 1.2.0(2026-05-05)

* SQL操作增加日志。
* MySQL支持SSH通道连接。
* 优化钉钉消息：`send_autotest_report()`更名为`send_summary()`方法。

## 1.1.0(2026-04-02)

* Web测试：脚手架增加ai模板示例。
* 接口测试：脚手架增加`SKILL.md`，模板项目工程化。
* YAML API 用例
    * 功能：增加断言数据。
    * 功能：增加`PATCH`请求方法。
    * 修复：YAML API 用例日志错误。
    * 修复：YAML API 用例保存变量错误。
    * 修复：`request_utils.py`导入包错误。

## 1.0.0(2026-03-02)

* Web测试：
    * 集成`autowing` AI 自动化测试库。
* 接口测试：
    * `base_url()` 函数该为 `base_url` 变量，更符合调用习惯。
    * 优化`@api()` 装饰器，专门用于 API 方法的装饰。
    * 修复：兼容macOS 系统用例的执行顺序问题。
* 功能：平台化支持，提供了API将用例解析成JSON，以及反向执行 JSON 用例。
* 功能：增加tomorrow模块，更简单的方式提供`threads()` 线程功能。
* 功能：支持参数化的参数显示到HTML测试报告中。
* 修复：`conftest.py` 中配置测试报告名称不生效的问题。
* 升级：`pytest-xhtml` 依赖库。
* 升级：`pytest-req` 依赖库。

## 0.8.0(2026-01-09)

* Web测试：
    * 增加 `playwright` 最新API。
* 接口测试
    * 增加`save_response()` 方法用于保存响应结果。
    * YAML支持`step`关键字用于描述测试步骤。
* 升级 pytest-html 测试库。

## 0.7.3(2025-12-12)

* `HttpRequest` 增加参数。
* `webhook.py` 格式化代码。
* 优化logo的打印方式。

## 0.7.2(2025-12-3)

* 修复bug
* 合并功能

## 0.7.1(2025-12-2)

* 代码优化
* 合并功能

## 0.7.0(2025-11-18)

* YAML API 更新：
    * 支持`centrifuge` 协议，公司内部使用。
    * `commons` 相关代码重构。
    * 测试步骤增加 `prescript` 字段，执行前置脚本。
    * 测试步骤增加 `sleep` 字段，支持用例执行完休眠。
    * 简化`test_api.py`脚本。
    * 增加新的断言类型：`greater`,`greater_equal`, `less`, `less_equal`。
* 使用新的模板
* 移除`jmespath`直接依赖。
* 升级`pytest-req` 到 0.5.0版本。

## 0.6.0(2025-10-23)

* 更新`lounger`命令，创建API测试，直接提供混合示例。
* 调整`YAML`接口测试用例的查找规则。
* 升级`pytest-xhtml>=0.2.0`最新版本。
* 增加`global_test_config()`函数，用于获取`config.yaml`中的配置。

## 0.5.0(2025-10-8)

* 支持YAML编写API测试，提供了一套完整的方案。

## 0.3.0(2025-08-27)

* 使用`pyest-xhtml`替换`pytest-html`报告，现代美观。
* 升级`pytest-playwright>=0.7.0`最新版本。
* 修复: `HTML` 报告无法集成`pytest-req`日志的问题。

## 0.2.0(2024-09-27)

* 增加`HttpRequest`类，支持`API objects`设计模式。
* 增加`BasePage`、`Locator`类，支持`Page objects`设计模式。
* 修复: `python 3.12` 警告：`datetime.utcnow()`废弃。

## 0.1.0(2024-09-13)

* lounger 正式发布
