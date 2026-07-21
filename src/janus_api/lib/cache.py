from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import (
    Any,
    Awaitable,
    Callable,
    Generic,
    Iterator,
    MutableMapping,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

logger = logging.getLogger(__name__)

# ---------------------------
# Type aliases
# ---------------------------
Listener = Callable[..., Union[Awaitable[Any], Any]]

K = TypeVar("K")
V = TypeVar("V")


# ---------------------------
# Cache
# ---------------------------
class Cache(MutableMapping[K, V], Generic[K, V]):
    def __init__(self, max_size: int = 1024, ttl: Optional[float] = None) -> None:
        self.max_size = int(max_size)
        self.ttl = float(ttl) if ttl is not None else None
        self._data: "OrderedDict[K, Tuple[V, Optional[float]]]" = OrderedDict()
        self._lock = threading.RLock()

    def _is_expired(self, key: K) -> bool:
        value, expires = self._data.get(key, (None, None))
        if expires is None:
            return False
        return time.time() > expires

    def _purge_if_expired(self, key: K) -> None:
        if key in self._data and self._is_expired(key):
            logger.debug("Cache: purging expired key %r", key)
            del self._data[key]

    def __getitem__(self, key: K) -> V:
        with self._lock:
            if key not in self._data:
                raise KeyError(key)
            self._purge_if_expired(key)
            if key not in self._data:
                raise KeyError(key)
            value, expires = self._data.pop(key)
            self._data[key] = (value, expires)
            return value

    def __setitem__(self, key: K, value: V) -> None:
        with self._lock:
            expires = (time.time() + self.ttl) if self.ttl is not None else None
            if key in self._data:
                self._data.pop(key)
            self._data[key] = (value, expires)
            while len(self._data) > self.max_size:
                evicted_key, _ = self._data.popitem(last=False)
                logger.debug("Cache: evicted %r", evicted_key)

    def __delitem__(self, key: K) -> None:
        with self._lock:
            del self._data[key]

    def __iter__(self) -> Iterator[K]:
        with self._lock:
            return iter(list(self._data.keys()))

    def __len__(self) -> int:
        with self._lock:
            keys = list(self._data.keys())
            for k in keys:
                self._purge_if_expired(k)
            return len(self._data)

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        try:
            return self[key]
        except KeyError:
            return default

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
