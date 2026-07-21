from __future__ import annotations

import asyncio
import logging
from typing import (
    Any,
    List,
    Optional,
)

from .handler import AsyncEventHandler

logger = logging.getLogger(__name__)


# ---------------------------
# Emitter
# ---------------------------
class AsyncEmitter:
    def __init__(self, handler: AsyncEventHandler, namespace: Optional[str] = None) -> None:
        self._handler = handler
        self._namespace = f"{namespace}." if namespace else ""

    async def emit(self, name: str, *args: Any, wait: bool = False, timeout: Optional[float] = None, **kwargs: Any) -> \
            List[Any]:
        event_name = f"{self._namespace}{name}"
        logger.debug("AsyncEmitter: emitting %r", event_name)
        return await self._handler.emit(event_name, *args, wait=wait, timeout=timeout, **kwargs)

    def emit_fire_and_forget(self, name: str, *args: Any, loop: Optional[asyncio.AbstractEventLoop] = None,
                             **kwargs: Any) -> None:
        loop = loop or asyncio.get_event_loop()
        loop.call_soon_threadsafe(asyncio.create_task, self.emit(name, *args, wait=False, **kwargs))
