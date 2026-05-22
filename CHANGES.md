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
