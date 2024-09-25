import json

from lounger.request import HttpRequest
from lounger.request import api


class UserApiObject(HttpRequest):
    """
    API Object
    """

    @api(describe="添加用例", status_code=200, ret="form.username")
    def add_user(self, username):
        r = self.post("/post", data={"username": username})
        return r

    @api(describe="删除用例", status_code=200, ret="data")
    def del_user(self, username):
        r = self.delete("/delete", json={"username": username})
        return r


def test_add_user(base_url):
    """test add user"""
    uao = UserApiObject(base_url)
    name = uao.add_user(username="tom")
    assert name == "tom"


def test_delete_user(base_url):
    """test delete user"""
    uao = UserApiObject(base_url)
    data = uao.del_user(username="tom")
    data_dict = json.loads(data)
    assert data_dict["username"] == "tom"
