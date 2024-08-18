from lounger import data


@data([1, 2, 3], scope="class")
class TestClass:
    def test_method(self, params):
        assert params > 0
