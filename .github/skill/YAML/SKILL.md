# Skill: 基于 Lounger 框架的 YAML 驱动 API 测试

## 核心理念

Lounger 框架同时支持 **Code 用例**（`test_dir/`）和 **YAML 用例**（`datas/`）。YAML 用例通过 `@load_teststeps()` 装饰器解析，最终由 pytest 统一执行。

YAML 用例文件名遵循 `test_*.yaml` 或 `*_test.yaml`。

---

## 项目结构

```shell
project_root/
├── config/
│   └── config.yaml                    # 全局配置（base_url、token、测试目录、全局变量）
├── datas/                             # YAML 测试用例
│   ├── global_setup/                  # 最先执行（如登录、环境初始化）
│   ├── testcase/                      # 用例目录（按模块分子目录，数字前缀控制顺序）
│   │   ├── 01_module_a/
│   │   └── 02_module_b/
│   └── global_teardown/               # 最后执行（可选）
├── scripts/                           # prescript 脚本目录
│   ├── db.py                          # 数据库助手（基于 Lounger MySQLDB.from_ssh_tunnel）
│   └── ...                            # 按业务子目录存放
├── test_api.py                        # YAML 用例运行入口
├── conftest.py                        # 共用的 fixture、自定义函数
└── test_dir/                          # Code 测试用例
```

---

## config.yaml 配置

```yaml
base_url: https://api-test.example.com

test_project:                          # 声明哪些目录被收集
  global_setup: True                   # 最先执行
  testcase/01_module_a: True
  testcase/02_module_b: True
  global_teardown: True                # 最后执行（可选）

global_test_config:                    # 所有用例通过 ${config(key)} 引用
  shop_id: 97585692989
  customer_rid: 9978799915325
  b_token: "Bearer eyJhbG..."
  request_interval_seconds: 3          # 每条用例间隔秒数

  # 数据库配置（conftest.py 和 prescript 脚本共用）
  ssh_host: x.x.x.x
  ssh_port: 22
  ssh_user: ubuntu
  ssh_private_key: /path/to/key.pem
  remote_db_host: 127.0.0.1
  remote_db_port: 3306
  db_user: root
  db_password: root
  db_database: test_db
  db_charset: utf8mb4
```

---

## conftest.py — 公共逻辑

`conftest.py` 同时服务 YAML 和 Code 用例，体现三种角色：

```python
from datetime import datetime
from pathlib import Path
import pytest

# 1. 自定义函数（YAML 中通过 ${函数名(参数)} 调用）
def today_str() -> str:
    """返回 "2026-06-03"。YAML: ${today_str()}"""
    return datetime.now().strftime("%Y-%m-%d")

def today_end_str() -> str:
    """返回 "2026-06-03T23:59:59+08:00"。YAML: ${today_end_str()}"""
    return datetime.now().strftime("%Y-%m-%dT23:59:59+08:00")

def add(n, m):
    """带参数示例：${add(1, 2)} → 3。也支持 ${add($extracted_id, 10)}"""
    return int(n) + int(m)

# 2. 通知钩子（可选）
def pytest_terminal_summary(terminalreporter, exitstatus, config):
    pass  # 按需实现钉钉/企业微信通知
```

> 需要更多工具函数（如签名、加密）时，按相同模式添加即可。

---

## YAML 用例编写

### 基本结构

一个 YAML 文件可包含多个 `teststeps` 块，每个块是一条独立用例：

```yaml
- teststeps:
    - step: 获取资源列表
      request:
        method: GET
        url: /api/v1/resources
        headers:
          Authorization: "${config(b_token)}"
        params:
          page: 1
      validate:
        equal:
          - ["status_code", 200]
```

### 步骤字段总览

| 字段 | 必需 | 说明 |
|------|------|------|
| `step` | 推荐 | 步骤描述（用于报告） |
| `request` | **是** | HTTP 请求（`method`、`url`、`headers`、`params`、`json`、`data`） |
| `validate` | 推荐 | 断言定义 |
| `extract` | 可选 | 从响应中提取变量，后续步骤通过 `${extract(key)}` 引用 |
| `sleep` | 可选 | 步骤完成后等待秒数 |
| `prescript` | 可选 | 前置脚本（Python 文件路径） |
| `presteps` | 可选 | 前置步骤列表（YAML 文件路径） |

### 多步骤用例

一条用例包含多个步骤，顺序执行（适合业务流程）：

```yaml
- teststeps:
    - step: 01 - 开启规则
      request:
        method: POST
        url: /consumer/api/v1/updateRule
        headers:
          Authorization: "${config(b_token)}"
        json:
          id: 1094
          status: 1
      validate:
        equal:
          - ["status_code", 200]

    - step: 02 - 检查积分流水（此时应不含目标记录）
      prescript: cleanup_order_reward_trace_data.py
      request:
        method: POST
        url: /consumer/api/v1/pointsHistory
        json:
          customer_rid: "${config(customer_rid)}"
      validate:
        not_contains:
          - ["body.data.customerPointWater[*].reason", "Place an order"]

    - step: 03 - 触发积分补发
      request:
        method: PUT
        url: /merchant/points/past/order
      validate:
        equal:
          - ["status_code", 204]
      sleep: 30

    - step: 04 - 再次检查（此时应包含目标记录）
      request:
        method: POST
        url: /consumer/api/v1/pointsHistory
        json:
          customer_rid: "${config(customer_rid)}"
      validate:
        contains:
          - ["body.data.customerPointWater[*].reason", "Place an order"]
```

---

## 变量引用

三种变量来源可以混用，优先级：`${extract}` > `${config}` > `${函数()}`

| 语法 | 来源 | 示例 |
|------|------|------|
| `${config(key)}` | `config.yaml` → `global_test_config` | `Authorization: "${config(b_token)}"` |
| `${函数名(args)}` | `conftest.py` 中定义 | `end_at: "${today_end_str()}"`、`id: "${add(1, 2)}"` |
| `${extract(key)}` | 步骤 `extract` 提取 / prescript `cache.set` | `url: /posts/${extract(second_id)}` |

**步骤内 extract 提取：**

```yaml
- teststeps:
    - step: 提取列表第二项的 id
      request:
        method: GET
        url: /posts
      extract:
        second_id: "[1].id"
    - step: 使用提取值
      request:
        method: GET
        url: /posts/${extract(second_id)}
```

**prescript 通过 cache.set 写入** — 详见下方 prescript 章节。

---

## 前置步骤（presteps）

引用另一个 YAML 文件作为前置操作：

```yaml
# datas/steps/login.yaml
- teststeps:
    - step: 用户登录
      request:
        method: POST
        url: /login
        data:
          username: admin
          password: pwd123
      extract:
        login_token: "data.token"

# 在用例中引用
- teststeps:
    - presteps:
        - steps/login.yaml
    - step: 获取用户信息
      request:
        method: GET
        url: /user/info
        headers:
          Authorization: ${extract(login_token)}
```

---

## 前置脚本（prescript）

prescript 是请求前执行的 Python 脚本，用于数据库准备或预期值查询。

### scripts/db.py — 数据库助手

基于 Lounger 封装的 `MySQLDB.from_ssh_tunnel()`，无需手动管理 SSH 连接：

```python
# scripts/db.py
from contextlib import contextmanager
from pathlib import Path
from lounger.db_operation import MySQLDB
from lounger.utils.variables import ExtractVar

_extractor = ExtractVar()

@contextmanager
def get_db():
    with MySQLDB.from_ssh_tunnel(
        ssh_host=_extractor.config("ssh_host"),
        ssh_port=int(_extractor.config("ssh_port")),
        ssh_user=_extractor.config("ssh_user"),
        ssh_private_key=str(Path(_extractor.config("ssh_private_key")).expanduser()),
        remote_db_host=_extractor.config("remote_db_host"),
        remote_db_port=int(_extractor.config("remote_db_port")),
        db_user=_extractor.config("db_user"),
        db_password=_extractor.config("db_password"),
        db_database=_extractor.config("db_database"),
        db_charset=_extractor.config("db_charset"),
        ssh_timeout=5,
    ) as db:
        yield db

def query_one(sql: str) -> dict | None:
    with get_db() as db:
        return db.query_one(sql)

def execute_many(sql_list: list[str]):
    with get_db() as db:
        for sql in sql_list:
            db.execute_sql(sql)
```

### 两种典型用法

**场景一：数据清理**（请求前清理脏数据）

```yaml
- teststeps:
    - step: 更新规则
      prescript: cleanup_by_extract_template.py    # ← 先清理
      request:
        method: POST
        url: /consumer/api/v1/updateRule
        json:
          id: 1094
          status: 0
```

```python
# scripts/reward_past_action/cleanup_by_extract_template.py
from lounger.utils.variables import ExtractVar
from scripts.db import execute_many

_extractor = ExtractVar()
customer_rid = _extractor.config("customer_rid")

execute_many([
    f"""DELETE FROM boom_customer_point_water
        WHERE customer_rid = {customer_rid} AND type = 5;""",
])
```

**场景二：查询预期值**（DB 数据作为断言 expected value）

```python
# scripts/analytics/loyalty_overview_widget_opens_select.py
from lounger.utils import cache
from lounger.utils.variables import ExtractVar
from scripts.db import query_one

_extractor = ExtractVar()
SHOP_ID = int(_extractor.config("shop_id"))

widget_opens_total = int((query_one(f"""
    SELECT COALESCE(SUM(count), 0) AS total_count
    FROM boom_widget_statistic
    WHERE shop_id = {SHOP_ID}
""") or {}).get("total_count") or 0)

cache.set({"widget_opens_total": widget_opens_total})
```

```yaml
- teststeps:
    - step: 概览数据与 DB 比对
      prescript: loyalty_overview_widget_opens_select.py
      request:
        method: GET
        url: /merchant/analytics/loyalty/overview
        headers:
          Authorization: "${config(b_token)}"
      validate:
        equal:
          - ["status_code", 200]
          - ["body.widget_opens", "${extract(widget_opens_total)}"]  # DB ↔ API
```

> 数据流：`scripts/db.py 查询 DB → cache.set({key: value}) → YAML 中 ${extract(key)}`

---

## 断言规范

| 方法 | 说明 | 示例 |
|------|------|------|
| `equal` | 精确相等 | `["status_code", 200]` |
| `not_equal` | 不相等（常用来判断非空） | `["body", null]` |
| `contains` | 包含子串 | `["body.message", "succ"]` |
| `not_contains` | 不包含子串 | `["body.data[*].reason", "error"]` |
| `length` / `greater` / `greater_equal` / `less` / `less_equal` | 数值比较 | `["body.id", 0]` |

**路径写法**（统一用 `body.` 前缀）：

| 表达式 | 说明 |
|--------|------|
| `status_code` | HTTP 状态码 |
| `body.success` | JSON 字段 |
| `body.data[0].id` | 数组首个元素 |
| `body.data[*].name` | 数组中所有元素的 name |
| `headers.Content-Type` | 响应头 |

```yaml
validate:
  equal:
    - ["status_code", 200]
    - ["body.success", true]
  not_equal:
    - ["body.data.name", ""]       # 非空
  contains:
    - ["body.data[*].reason", "已激活"]
```

---

## 常见反模式

- 在 YAML 中硬编码 token → 用 `${config(b_token)}`
- 断言不带前缀 → 写 `body.xxx` 而非裸 `xxx`
- 一个 YAML 混多模块接口 → 按模块拆分文件
- 复杂编排放 YAML → 交给 Code 用例

---

**版本**: v1.0
**日期**: 2026-06-03
