# -*- coding: utf-8 -*-
"""简易内存缓存：减少重复请求气象API。进程级、带 TTL。"""
import time
import threading


class SimpleCache:
    def __init__(self, ttl=600):
        self._store = {}
        self._lock = threading.Lock()
        self.ttl = ttl

    def get(self, key):
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            if time.time() - item["ts"] > self.ttl:
                self._store.pop(key, None)
                return None
            return item["value"]

    def set(self, key, value):
        with self._lock:
            self._store[key] = {"value": value, "ts": time.time()}

    def clear(self):
        with self._lock:
            self._store.clear()


weather_cache = SimpleCache(ttl=600)
