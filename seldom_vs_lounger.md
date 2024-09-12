## seldom vs pytest

seldom 是建立在 unittest单元测试框架的基础上的自动化测试框架，内置了非常多的功能达到开箱即用，并且支持 seldom-platform平台化。
> seldom有一些先天的不足，例如在 并发方面，内置selenium的运行较慢等。

lounger 是建立在 pytest单元测试框架的基础上的自动化测试框架，移植了seldom的部分功能，结合pytest的功能和生态优势开发，同样达到开箱即用。
> lounger也并非完美无缺，内置的`pytest-html`样式和功能还有改进空间，不支持平台化。

* seldom VS lounger

> 这里仅罗列功能对比，至于选哪个，请自行结合业务和需求。

| 功能            | seldom | 说明(3.9.0版本)                               | lounger | 说明(0.1.0版本)                              |
|---------------|--------|-------------------------------------------|---------|------------------------------------------|
| 基于单元框架        | 🪨     | unittest                                  | 🪨      | pytest                                   |
| web UI测试      | ✅      | 集成selenium，并二次开发 I️                       | ✅       | 集成`pytest-playwright`                    |
| web UI断言      | ✅      | 内置（assertText、assertTitle、assertElement）等 | ✅       | `playwright`提供丰富断言                       |
| Page Object模式 | ❌      | 未内置，推荐poium库                              | ❌       | 未内置，推荐`poium`                            |
| API 测试        | ✅      | 集成Requests，并二次开发                          | ✅       | 集成`pytest-req`                           |
| API 断言        | ✅      | 内置（assertJSON、assertPath、assertSchema）等   | ✅       | `pytest-req`提供断言                         |
| App UI测试      | ✅      | 集成Appium，并二次开发 I️                         | ❌       | 未集成App测试库                                |
| 脚手架           | ✅      | 支持快速创建Web/App/API项目                       | ✅       | 支持快速创建Web/API项目                          |
| HTML测试报告      | ✅      | 集成XTestRunner支持                           | ✅       | 集成`pytest-html`支持                        |
| HTML显示失败截图    | ✅      | 用例`失败`/`错误`自动截图                           | ✅       | lounger已对`pytest-html`进行了默认配置            |
| HTML显示日志      | ✅      | Seldom默认支持                                | ✅       | lounger已对`pytest-html`进行了默认配置            |
| XML测试报告       | ✅      | 集成XTestRunner支持                           | ✅       | 自带 `--junit-xml`参数支持                     |
| log日志         | ✅      | 集成luguru支持                                | ✅       | 集成luguru支持                               |
| 发送测试结果/消息     | ✅      | 支持（email、钉钉、飞书、微信）等                       | ❌       | 不支持                                      |
| 失败重跑          | ✅      | 使用`rerun`参数配置                             | ✅       | 集成`pytest-rerunfailures`                 |
| 随机测试数据        | ✅      | 支持`testdata`                              | ✅       | 支持`testdata`                             |
| 数据库操作         | ✅      | 支持（sqlite3、MySQL、SQL Server）等             | ✅       | 支持（sqlite3、MySQL、SQL Server）等            |
| cache缓存       | ✅      | 内置(cache、memory_cache、dis_cache)等         | ✅       | 内置(cache、memory_cache、dis_cache)等        |
| 用例依赖          | ✅      | 内置`@depend()`                             | ✅       | 内置`@pytest.mark.dependency()`            |
| 用例分类标签        | ✅      | 内置`@label()`                              | ✅       | 支持`@pytest.mark.xxx`标签                   |
| 数据驱动方法        | ✅      | 内置`@data()`                               | ✅       | 内置`@data()`                              |
| 数据驱动文件        | ✅      | 内置`@file_data()`支持(JSON\YAML\CSV\Excel)等  | ✅       | 内置`@file_data()`支持(JSON\YAML\CSV\Excel)等 |
| 钩子函数          | ✅      | `confrun.py`用例运行钩子                        | ✅       | `conftest.py`、`pytest.ini`等功能更强大         |
| 命令行工具CLI      | ✅      | `seldom`命令                                | ✅       | `pytest`命令                               |
| 并发执行          | ⚠️     | 内置`@threads`手动分配线程                        | ✅       | 集成pytest-xdist，自动分配，更强大                  |
| 平台化           | ✅      | 支持（seldom-platform）平台                     | ❌       | 不支持                                      | 
| 第三方插件         | ⚠️     | 插件很少，扩展能力差。                               | ✅       | 有上千个插件，扩展能力强                             |

__说明__

* ✅  : 表示支持。
* ❌  : 表示不支持，表示框架没有该功能，第三方插件也没有。
* ⚠️  : 表示支持的不好，或没有对方好。
