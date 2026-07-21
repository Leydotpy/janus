from __future__ import annotations

import asyncio
import logging
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Union,
)

from .dispatcher import AsyncDispatcher, default_async_dispatcher

logger = logging.getLogger(__name__)

# ---------------------------
# Type aliases
# ---------------------------
Listener = Callable[..., Union[Awaitable[Any], Any]]


# ---------------------------
# Event handler
# ---------------------------
class AsyncEventHandler:
    def __init__(self, dispatcher: Optional[AsyncDispatcher] = None) -> None:
        self._listeners: Dict[str, Set[Listener]] = {}
        self._lock = asyncio.Lock()
        self._dispatcher = dispatcher or default_async_dispatcher

    async def add_listener(self, event: str, callback: Listener) -> None:
        async with self._lock:
            self._listeners.setdefault(event, set()).add(callback)
            logger.debug("AsyncEventHandler: added listener %r -> %r", event, callback)

    async def remove_listener(self, event: str, callback: Listener) -> None:
        async with self._lock:
            s = self._listeners.get(event)
            if s and callback in s:
                s.remove(callback)
                if not s:
                    del self._listeners[event]
                logger.debug("AsyncEventHandler: removed listener %r -> %r", event, callback)

    async def emit(
            self,
            event: str,
            *args: Any,
            wait: bool = False,
            timeout: Optional[float] = None,
            **kwargs: Any,
    ) -> List[Any]:
        async with self._lock:
            listeners = list(self._listeners.get(event, set()))
        if not listeners:
            logger.debug("AsyncEventHandler: no listeners for %r", event)
            return [] if wait else []

        futures: List[asyncio.Future] = []
        for cb in listeners:
            futs = await self._dispatcher.dispatch_single(cb, *args, wait=False, timeout=None, **kwargs)
            for f in futs:
                if isinstance(f, asyncio.Future):
                    futures.append(f)
                else:
                    futures.append(asyncio.ensure_future(f))  # type: ignore[arg-type]

        if wait:
            # wait for completion (we rely on asyncio.wait instead of as_completed to support timeout)
            done, pending = await asyncio.wait(futures, timeout=timeout, return_when=asyncio.ALL_COMPLETED)
            results: List[Any] = []
            for d in done:
                try:
                    results.append(d.result())
                except Exception:
                    logger.exception("AsyncEventHandler: listener raised when awaiting results")
                    results.append(None)
            # cancel leftover
            for p in pending:
                p.cancel()
            return results

        return futures

    async def shutdown(self, wait: bool = True, timeout: Optional[float] = None) -> None:
        """
        Shutdown event handler by delegating to the dispatcher to drain pending tasks and shutdown executor.
        """
        logger.info("AsyncEventHandler: shutdown(wait=%s, timeout=%s)", wait, timeout)
        await self._dispatcher.shutdown(wait=wait, timeout=timeout)


# default handler
global_async_handler = AsyncEventHandler()