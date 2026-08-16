"""
lounger cache — disk JSON cache, memory LRU cache and disk-pickle decorator.

Semantics (docs/development_plan.md §3.10):

- The disk cache is a single JSON file shared across test processes
  (``tempfile.gettempdir()/cache_data.json`` by default). Because tests run
  in (possibly) separate processes, **cached values survive between runs**;
  call ``cache.clear()`` between tests that must not share state.
- Optional TTL: ``cache.set({"k": v}, ttl=60)`` expires the value after 60s
  (lazy: checked on ``get``).
- Optional namespace: ``cache.set({"k": v}, namespace="myproject")`` stores
  under ``myproject:k``; ``get("k", namespace="myproject")`` reads it. The
  default (``namespace=None``) keeps the legacy flat behavior.
- All mutations are guarded by a module-level lock; reads/writes are
  thread-safe within a process (cross-process safety relies on the lock in
  each process + atomic-ish whole-file rewrite).
"""
import json
import os
import pickle
import shutil
import tempfile
import threading
import time
import uuid
from functools import lru_cache
from functools import wraps as func_wraps

from pytest_req.log import log

DATA_PATH = os.path.join(tempfile.gettempdir(), "cache_data.json")

#: Marker keys used to wrap values with an expiry timestamp.
_VALUE_KEY = "__v__"
_EXPIRES_KEY = "__exp__"


class Cache:
    """
    Disk Cache through JSON files.
    """

    _lock = threading.Lock()  # 类级别锁，保证进程内线程安全

    def __init__(self):
        is_exist = os.path.isfile(DATA_PATH)
        if is_exist is False:
            with open(DATA_PATH, "w", encoding="utf-8") as json_file:
                json.dump({}, json_file)

    @staticmethod
    def _wrap(value, ttl):
        """Wrap a value with an optional expiry timestamp."""
        entry = {_VALUE_KEY: value}
        if ttl is not None:
            entry[_EXPIRES_KEY] = time.time() + ttl
        return entry

    @staticmethod
    def _unwrap(entry):
        """
        Return the stored value, or None if the entry is missing/expired.

        Legacy raw values (stored without the wrapper by older versions) are
        returned as-is for backward compatibility.
        """
        if entry is None:
            return None
        if isinstance(entry, dict) and _VALUE_KEY in entry:
            expires = entry.get(_EXPIRES_KEY)
            if expires is not None and time.time() > expires:
                return None
            return entry[_VALUE_KEY]
        return entry  # legacy raw value

    @staticmethod
    def _key(name, namespace):
        """Apply the optional namespace prefix (``<namespace>:<key>``)."""
        if namespace is None:
            return name
        return f"{namespace}:{name}"

    @staticmethod
    def _read_all():
        """Read the whole cache file (dict)."""
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except (OSError, ValueError):
            pass
        return {}

    @staticmethod
    def _write_all(data: dict) -> None:
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    @classmethod
    def clear(cls, name: str | None = None, namespace: str | None = None) -> None:
        """
        Clear cached data.

        :param name: Key to clear; ``None`` clears everything.
        :param namespace: Optional namespace prefix.
        """
        with cls._lock:
            if name is None:
                cls._write_all({})
                log.info("💾 Clear all cache data.")
                return

            key = cls._key(name, namespace)
            save_data = cls._read_all()
            if key in save_data:
                del save_data[key]
                log.info(f"💾 Clear cache data: {key}")
                cls._write_all(save_data)

    @classmethod
    def set(cls, data: dict, ttl: float | None = None, namespace: str | None = None) -> None:
        """
        Set cached data.

        :param data: Mapping of ``key -> value`` to store.
        :param ttl: Optional TTL in seconds; the value expires after that.
        :param namespace: Optional namespace prefix (``<namespace>:<key>``).
        """
        with cls._lock:
            save_data = cls._read_all()
            for key, value in data.items():
                stored_key = cls._key(key, namespace)
                if stored_key not in save_data:
                    log.info(f"💾 Set cache data: {key} = {value}")
                else:
                    log.info(f"💾 Update cache data: {key} = {value}")
                save_data[stored_key] = cls._wrap(value, ttl)

            cls._write_all(save_data)

    @classmethod
    def get(cls, name=None, namespace: str | None = None):
        """
        Get cached data.

        :param name: Key to read; ``None`` returns the whole cache.
        :param namespace: Optional namespace prefix.
        :return: The stored value, or None if missing/expired.
        """
        with cls._lock:
            save_data = cls._read_all()
            if name is None:
                # unwrap every entry (drop expired ones) for a clean view
                view = {
                    key: cls._unwrap(entry)
                    for key, entry in save_data.items()
                    if cls._unwrap(entry) is not None
                }
                log.info(f"💾 Get all cache data: {view}")
                return view

            key = cls._key(name, namespace)
            value = cls._unwrap(save_data.get(key))
            if value is not None:
                log.info(f"💾 Get cache data: {name} = {value}")
            return value


cache = Cache()


def memory_cache(maxsize=None, typed=False):
    """ memory (Least-recently-used) cache decorator
    """
    return lru_cache(maxsize=maxsize, typed=typed)


class DiskCache:
    """
    Cache data to disk decorator.
    """

    _NAMESPACE = uuid.UUID("c875fb30-a8a8-402d-a796-225a6b065cad")

    def __init__(self, cache_path: str | None = None, ttl: float | None = None):
        """
        :param cache_path: Directory for cache files.
        :param ttl: Optional TTL in seconds; a cached file older than this is
            treated as expired and the wrapped function is re-run.
        """
        if cache_path:
            self.cache_path = os.path.abspath(cache_path)
        else:
            self.cache_path = os.path.join(tempfile.gettempdir(), ".diskcache")
        self.ttl = ttl

    def _cache_file(self, func, args, kw):
        params_uuid = uuid.uuid5(self._NAMESPACE, "-".join(map(str, (args, kw))))
        key = '{}-{}.cache'.format(func.__name__, str(params_uuid))
        return os.path.join(self.cache_path, key)

    def _is_fresh(self, cache_file) -> bool:
        if self.ttl is None:
            return True
        try:
            return (time.time() - os.path.getmtime(cache_file)) < self.ttl
        except OSError:
            return False

    def __call__(self, func):
        """
        Returns a wrapped function.
        If there is no cache on disk, the function is called to get the result, cached and returned
        If there is a cache on the disk, the cached result is returned directly
        :param func:
        """

        @func_wraps(func)
        def wrapper(*args, **kw):
            """
            wrapper
            """
            if not os.path.exists(self.cache_path):
                os.makedirs(self.cache_path)

            cache_file = self._cache_file(func, args, kw)

            try:
                if self._is_fresh(cache_file):
                    with open(cache_file, 'rb') as f:
                        return pickle.load(f)
            except BaseException as msg:
                log.warning(msg)

            val = func(*args, **kw)
            try:
                with open(cache_file, 'wb') as f:
                    pickle.dump(val, f)
            except BaseException as msg:
                log.warning(msg)
            return val

        return wrapper

    def clear(self, func_name: str | None = None) -> None:
        """
        clear function cache
        :param func_name:
        :return:
        """
        if func_name is None:
            log.info("💾 Clear all function cache")
            if os.path.exists(self.cache_path):
                shutil.rmtree(self.cache_path)
        else:
            log.info(f"💾 Clear function cache: {func_name}")
            if not os.path.exists(self.cache_path):
                return
            for cache_file in os.listdir(self.cache_path):
                if cache_file.startswith(func_name + "-"):
                    os.remove(os.path.join(self.cache_path, cache_file))


disk_cache = DiskCache
