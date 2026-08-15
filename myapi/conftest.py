from lounger.runtime import register_template_func


def pytest_xhtml_report_title(report):
    report.title = "Lounger Test Report"


def id_add_one(rid):
    return int(rid) + 1


# 显式注册模板函数（替代旧的 conftest 自动扫描方式）
register_template_func("id_add_one", id_add_one)
