"""
Mongo DB API
"""


def _get_mongo_client():
    """
    Import pymongo lazily so this module can be imported without the driver.
    The error only surfaces when a connection is actually created.
    """
    try:
        from pymongo import MongoClient
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(
            "pymongo is required for MongoDB support. "
            "Install with: pip install lounger[db-mongo]"
        ) from e
    return MongoClient


class MongoDB:
    """Mongo DB table API"""

    def __new__(cls, host: str, port: int, db: str):
        """
        Connect the mongodb database
        """
        MongoClient = _get_mongo_client()
        client = MongoClient(host, port)
        db_obj = client[db]
        return db_obj


if __name__ == '__main__':
    mongo_db = MongoDB("localhost", 27017, "yapi")
    col = mongo_db.list_collection_names()
    print("collection list: ", col)
    data = mongo_db.project.find_one()
    print("table one data:", data)
