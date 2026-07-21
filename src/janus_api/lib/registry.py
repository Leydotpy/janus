from __future__ import annotations

import logging
import threading
from typing import (
    Dict,
    Iterator,
    MutableMapping,
    Optional,
    Type,
)

logger = logging.getLogger(__name__)


# ---------------------------
# Registry
# ---------------------------
class Registry[TPlugin](MutableMapping[str, Type[TPlugin]]):
    _ready = False

    def __init__(self) -> None:
        self._map: Dict[str, Type[TPlugin]] = {}
        self._lock = threading.RLock()
        self._ready = False

    def register(self, identifier: str, cls: Type[TPlugin]) -> None:
        if not identifier or not isinstance(identifier, str):
            raise ValueError("identifier must be a non-empty string")
        with self._lock:
            if identifier in self._map:
                logger.warning("Registry: overwriting identifier %r", identifier)
            self._map[identifier] = cls
            logger.debug("Registry: registered %r -> %s", identifier, cls.__name__)

    def unregister(self, identifier: str) -> None:
        with self._lock:
            if identifier in self._map:
                del self._map[identifier]

    def get(self, identifier: str) -> Optional[Type[TPlugin]]:
        with self._lock:
            return self._map.get(identifier)

    def __getitem__(self, key: str) -> Type[TPlugin]:
        with self._lock:
            return self._map[key]

    def __setitem__(self, key: str, value: Type[TPlugin]) -> None:
        self.register(key, value)

    def __delitem__(self, key: str) -> None:
        self.unregister(key)

    def __iter__(self) -> Iterator[str]:
        with self._lock:
            return iter(list(self._map.keys()))

    def __len__(self) -> int:
        with self._lock:
            return len(self._map)
