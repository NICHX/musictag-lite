"""进程内 TTL 缓存：用于刮削网络响应，避免重复请求（§9.3「网络层统一出口」）。

设计文档里的 ``http_cache_ttl`` 需要一个落点：所有 Provider 经同一缓存，
以 ``(url, params)`` 为键缓存成功响应与 404，重复查询（翻队列、重搜、重取封面）
即可命中，无需再打网络，也就绕开了 MusicBrainz 1 req/s 的限速等待。
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any


class TTLCache:
    """带 TTL 与容量上限的线程安全内存缓存（超容量时按插入顺序淘汰最旧项）。"""

    def __init__(self, ttl: float, maxsize: int = 512) -> None:
        self._ttl = ttl
        self._maxsize = maxsize
        self._data: OrderedDict[Any, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Any) -> tuple[bool, Any]:
        """返回 ``(是否命中, 值)``；过期项视为未命中并顺手清理。"""
        now = time.monotonic()
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return False, None
            expires_at, value = item
            if expires_at <= now:
                self._data.pop(key, None)
                return False, None
            return True, value

    def set(self, key: Any, value: Any) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + self._ttl, value)
            self._data.move_to_end(key)
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


_shared_cache: TTLCache | None = None
_shared_lock = threading.Lock()


def response_cache() -> TTLCache:
    """全局共享的响应缓存单例（TTL 取自 ``settings.http_cache_ttl``）。"""
    global _shared_cache
    if _shared_cache is None:
        from app.core.config import get_settings

        with _shared_lock:
            if _shared_cache is None:
                _shared_cache = TTLCache(ttl=float(get_settings().http_cache_ttl), maxsize=512)
    return _shared_cache
