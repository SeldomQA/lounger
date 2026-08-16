# Lounger 业务项目开发指南（project_guide）

> 对应 `docs/development_plan.md` P2"官方推荐扩展方式文档"（thinking #1/#2/#10）。
> 配套阅读：[plugin_hooks.md](./plugin_hooks.md)（扩展点）、[run_json.md](./run_json.md)（平台执行协议）。

本文是**业务测试项目**的推荐开发方式：怎么组织目录、`conftest.py` 里能放什么、配置怎么读、扩展逻辑往哪写。

---

## 一、三层边界

| 层 | 是谁 | 放什么 | 典型内容 |
|---|---|---|---|
| **框架内核** | `lounger` 包 | 引擎、协议、断言、PO 封装、web_runner、services | **不要改**（除非提 PR） |
| **项目配置层** | 业务项目根 | 配置、用例、脚手架支持文件 | `config/config.yaml`、`datas/**/test_*.yaml`、`test_dir/`、`support/` |
| **业务扩展层** | 业务项目的 conftest / support / api 目录 | fixture、hook 注册、API Object、数据工厂 | `conftest.py`、`support/db.py`、`support/notify.py`、`api/clients/*.py` |

**边界规则**：业务逻辑只写在"项目配置层"与"业务扩展层"；框架内核只通过官方扩展点（settings / plugin_hooks / runtime / fixtures）交互。

## 二、`conftest.py` 只允许放三类东西

`conftest.py`（项目根 + `test_dir/`）里**只能**出现：

1. **fixture**（`@pytest.fixture`）：数据库连接、API client、env 配置等；
2. **pytest hook**（`pytest_*`）：自定义报告标题等；
3. **少量 helper 导入注册**：模板函数注册（`register_template_func`）、扩展点 hook 注册（`plugin_hooks`）、通知注册（`register_dingtalk_integration`）。

### 推荐 ✅ / 不推荐 ❌ 清单

| 推荐 | 不推荐 |
|---|---|
| `@pytest.fixture` 提供 `posts_api` / `mysql_db` | 在 conftest 里直接写请求逻辑、断言逻辑 |
| `register_template_func("random_email", ...)` | 定义一堆业务函数靠自动扫描隐式注册 |
| `register_before_execute_step(...)` 做请求前打点 | `monkey patch` / 直接替换 `lounger.case.execute_step` |
| `register_after_case_finish(...)` 做用例级通知 | 把钉钉 webhook 调用硬编码进 conftest 顶层 |
| `settings.get("base_url")` 读取配置 | `import yaml; yaml.safe_load(open("config/config.yaml"))` |
| `create_mysql_fixture(...)` 一行接数据库 | 手写 connect / close / SSH 隧道逻辑 |

> 依据：thinking.md #10 的表述（推荐/不推荐清单）。

## 三、配置统一走 `settings`

**不要**直接读 `config/config.yaml` 文件结构。统一通过 `lounger.settings`：

```python
from lounger.settings import settings

base_url = settings.get("base_url")                       # 顶层 key
var_one = settings.get("var_one", node="global_test_config")  # 节点内 key
port = settings.get_int("port", node="global_test_config")
enabled = settings.get_bool("enabled", node="global_test_config")
```

**机制**（3.4 落地）：

- **项目根锚定**：`config/config.yaml` 从 CWD 向上查找，换目录执行不丢配置；
- **mtime 缓存**：编辑配置后无需重启进程，下次 `get` 自动读到新值；
- **环境变量覆盖**：`LOUNGER_BASE_URL=...` / `LOUNGER_GLOBAL_TEST_CONFIG__VAR_ONE=...`
  （`LOUNGER_<NODE>__<KEY>`）优先于 YAML；
- **惰性 `base_url`**：`from lounger.commons.load_config import base_url` 同时支持
  `base_url()` 调用与 `f"{base_url}/path"` 值用法。

`yaml` 直接读取仅用于极少数脚手架场景（如支持文件解析），业务代码禁止。

## 四、模板函数显式注册

YAML 用例里的 `${func_name(args)}` 只能使用**显式注册**的函数：

```python
# conftest.py
from lounger.runtime import register_template_func

def random_email():
    return "user@example.com"

register_template_func("random_email", random_email)
```

- 注册点：`lounger.runtime.register_template_func`（官方 API）；
- 兼容 `LOUNGER_TEMPLATE_FUNCTIONS` dict 显式注册表；
- 旧的"自动扫描 conftest 所有函数"方式已**弃用**（DeprecationWarning），不要再依赖。

## 五、执行链扩展走 hook，禁止 monkey patch

请求前后加逻辑、失败附加动作、用例级通知，全部走 `lounger.plugin_hooks` 扩展点：

```python
from lounger.plugin_hooks import (
    register_after_case_finish,
    register_after_execute_step,
    register_before_execute_step,
    register_on_execute_step_error,
)

@register_before_execute_step
def log_start(case_step):
    log.info(f"▶ {case_step.get('name')}")

@register_after_execute_step
def log_end(case_step, resp):
    log.info(f"✓ {case_step.get('name')} — {getattr(resp, 'status_code', '?')}")

@register_on_execute_step_error
def notify_error(case_step, exc):
    log.error(f"✗ {case_step.get('name')} — {exc}")

@register_after_case_finish
def notify_case(result):
    # TestRunResult(nodeid, status, duration, description)
    log.info(f"📦 {result.nodeid} → {result.status}")
```

**禁止**：`lounger.case.execute_step = patched` 这类 monkey patch。完整注册方式、优先级与共存规则见 [plugin_hooks.md](./plugin_hooks.md)。

## 六、脚手架示例

用 `lounger` CLI 生成项目骨架即可获得本指南的**可运行示例**：

```bash
lounger create demo_api   # 或: lounger create demo_web
cd demo_api
pytest -v
```

脚手架 `lounger/project_temp/` 已包含：

- `conftest.py` —— 报告标题 + 通知/模板函数/执行链 hook 注释示例；
- `test_dir/conftest.py` —— fixture（`env_config` / `posts_api`）+ 数据库 fixture 注释示例；
- `api/clients/posts_api.py` —— `HttpRequest + @api` 分层 API Object；
- `datas/sample/test_sample.yaml` —— YAML 用例；
- `support/db.py` / `support/notify.py` —— 脚手架支持文件。

> 更多平台化执行（收集 → `--run-json` 执行 → 回传）见 [run_json.md](./run_json.md) 与
> `myapi/platform_running.py`。
