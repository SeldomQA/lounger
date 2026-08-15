from lounger import file_data


@file_data("json_data.json", key="name")
def test_json_list(params):
    """
    used file_data test
    """
    print(params)


@file_data("json_data.json", key="login")
def test_json_dict(params):
    """
    used file_data test
    """
    print(params)


@file_data("yaml_data.yaml", key="name")
def test_yaml_list(params):
    """
    used file_data test
    """
    print(params)


@file_data("yaml_data.yaml", key="login")
def test_yaml_dict(params):
    """
    used file_data test
    """
    print(params)


@file_data("csv_data.csv", line=2)
def test_csv(params):
    """
    used file_data test
    """
    print(params)


@file_data(file="excel_data.xlsx", sheet="Sheet1", line=2)
def test_excel(params):
    """
    used file_data test
    """
    print(params)
