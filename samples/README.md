# lounger基础示例

lounger框架集成许多基本的功能，当前目录下即是单元测试，也是使用示例。

| 文件名                         | 说明                                              |
|-----------------------------|-------------------------------------------------|
| `test_ai_web.py`            | Web测试：基于Auto-wing实现AI测试                         |
| `test_playwright.py`        | Web测试：基于Playwright 自动化浏览器测试                     |
| `test_page_object.py`       | 页面对象模型（Page Object Pattern）的封装与交互测试（用于 Web 自动化） |
| `test_request.py`           | 封装的 HTTP 请求客户端测试                                |
| `test_api_object.py`        | API对象模型（API object pattern）封装的对象模型（用于API 自动化）   |
| `test_cache_disk.py`        | 测试磁盘缓存功能（如缓存持久化、读写、过期清理等）                       |
| `test_cache_memory.py`      | 测试内存缓存机制（如 LRU 缓存、线程安全访问等）                      |
| `test_cache.py`             | 通用缓存接口或混合缓存策略的集成测试                              |
| `test_db_mssql.py`          | 针对 Microsoft SQL Server 的数据库连接与操作测试             |
| `test_db_mysql.py`          | 针对 MySQL 数据库的连接、查询、事务等功能测试                      |
| `test_db_postgresdb.py`     | 针对 PostgreSQL 数据库的功能与兼容性测试                      |
| `test_db_sqlite3.py`        | 针对 SQLite 轻量级数据库的本地存储与迁移测试                      |
| `test_dependence.py`        | 测试模块/用例间的依赖关系管理（如 pytest-dependency 或自定义依赖逻辑）   |
| `test_log.py`               | 日志系统测试（如日志级别、格式、文件输出、异常追踪等）                     |
| `test_marks_env.py`         | 测试环境标记（如 `@pytest.mark.env("prod")`）与条件执行逻辑     |
| `test_random_data.py`       | 随机数据生成器测试（如姓名、手机号、身份证等 mock 数据生成）               |
| `test_params_class_data.py` | 数据驱动，基于类属性提供测试参数的数据驱动方式                         |
| `test_params_data.py`       | 测试驱动，通用参数化测试数据                                  |
| `test_params_file_data.py`  | 数据驱动，从外部文件（JSON/CSV/YAML）加载测试数据的参数化测试           |
