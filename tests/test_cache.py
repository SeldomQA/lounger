"""
Cache semantics tests (docs/development_plan.md §3.10).

Covers:

- legacy behavior: set/get/clear with raw values stays compatible;
- TTL: values expire lazily on get;
- namespace: ``<namespace>:<key>`` isolation;
- concurrency: concurrent set/get from multiple threads does not lose data;
- DiskCache: TTL expiry + clear.
"""
import os
import threading
import time

import pytest

from lounger.utils import cache
from lounger.utils.cache import DiskCache


@pytest.fixture(autouse=True)
def _clean_cache():
    """Each test starts from an empty cache file."""
    cache.clear()
    yield
    cache.clear()


# ── legacy behavior (backward compatible) ─────────────────────────────────

def test_legacy_set_get_raw_values():
    cache.set({"key1": "value1", "key2": [1, 2, 3]})

    assert cache.get("key1") == "value1"
    assert cache.get("key2") == [1, 2, 3]


def test_legacy_clear_single_key():
    cache.set({"a": 1, "b": 2})
    cache.clear("a")

    assert cache.get("a") is None
    assert cache.get("b") == 2


def test_legacy_clear_all_and_get_all():
    cache.set({"a": 1})
    cache.clear()

    assert cache.get() == {}


def test_legacy_dict_value_not_confused_with_wrapper():
    """A plain dict stored as a value must survive the wrapper format."""
    cache.set({"user": {"name": "tom"}})

    assert cache.get("user") == {"name": "tom"}
    assert isinstance(cache.get("user"), dict)


# ── TTL ───────────────────────────────────────────────────────────────────

def test_ttl_expires_value(monkeypatch):
    import importlib
    cache_module = importlib.import_module("lounger.utils.cache")

    cache.set({"token": "abc"}, ttl=1)

    assert cache.get("token") == "abc"

    # simulate 2s passing (patch the time module used by the cache)
    real_time = time.time
    monkeypatch.setattr(cache_module.time, "time", lambda: real_time() + 2)

    assert cache.get("token") is None


def test_ttl_no_expiry_when_not_set():
    cache.set({"token": "abc"})  # no ttl → never expires

    assert cache.get("token") == "abc"


# ── namespace ─────────────────────────────────────────────────────────────

def test_namespace_isolates_keys():
    cache.set({"token": "project-a"}, namespace="proj_a")
    cache.set({"token": "project-b"}, namespace="proj_b")

    assert cache.get("token", namespace="proj_a") == "project-a"
    assert cache.get("token", namespace="proj_b") == "project-b"
    # flat namespace sees nothing (keys are prefixed)
    assert cache.get("token") is None


def test_namespace_clear_single_key():
    cache.set({"a": 1}, namespace="proj")
    cache.clear("a", namespace="proj")

    assert cache.get("a", namespace="proj") is None


def test_flat_and_namespaced_keys_coexist():
    cache.set({"k": "flat"})
    cache.set({"k": "nsp"}, namespace="ns")

    assert cache.get("k") == "flat"
    assert cache.get("k", namespace="ns") == "nsp"


# ── concurrency ───────────────────────────────────────────────────────────

def test_concurrent_set_does_not_lose_data():
    n_threads = 8
    per_thread = 25

    def writer(offset):
        for i in range(per_thread):
            cache.set({f"key_{offset}_{i}": i})

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # every key written by every thread is present
    for t in range(n_threads):
        for i in range(per_thread):
            assert cache.get(f"key_{t}_{i}") == i


def test_concurrent_readers_while_writing():
    stop = threading.Event()
    errors = []

    def writer():
        for i in range(50):
            cache.set({"w": i})
            if stop.is_set():
                return

    def reader():
        try:
            while not stop.is_set():
                cache.get("w")
                cache.get("missing_key_xyz")
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=writer)] + [
        threading.Thread(target=reader) for _ in range(4)
    ]
    for t in threads:
        t.start()
    time.sleep(0.2)
    stop.set()
    for t in threads:
        t.join()

    assert not errors


# ── DiskCache TTL ─────────────────────────────────────────────────────────

def test_disk_cache_ttl_expiry(tmp_path):
    d = DiskCache(cache_path=str(tmp_path), ttl=0.05)

    calls = {"n": 0}

    @d
    def compute(x):
        calls["n"] += 1
        return x * 2

    assert compute(21) == 42
    assert calls["n"] == 1
    # within TTL → cached
    assert compute(21) == 42
    assert calls["n"] == 1

    time.sleep(0.1)
    # past TTL → recomputed
    assert compute(21) == 42
    assert calls["n"] == 2


def test_disk_cache_without_ttl_caches_forever(tmp_path):
    d = DiskCache(cache_path=str(tmp_path))  # no ttl

    calls = {"n": 0}

    @d
    def compute(x):
        calls["n"] += 1
        return x

    compute(1)
    compute(1)
    assert calls["n"] == 1


def test_disk_cache_clear(tmp_path):
    d = DiskCache(cache_path=str(tmp_path))

    @d
    def compute(x):
        return x

    compute(1)
    assert os.path.exists(tmp_path)
    d.clear()
    assert not os.path.exists(tmp_path)
