from __future__ import annotations

import asyncio
import logging
from typing import (
    Any,
    Awaitable,
    List,
    Optional,
)

from janus_api.lib.events.handler import global_async_handler
from janus_api.lib.plugins.base import PluginMeta

logger = logging.getLogger(__name__)


# ---------------------------
# Shutdown helper - awaits plugin cleanup and handler shutdown
# ---------------------------
async def shutdown_all(timeout: Optional[float] = None, clear_cache: bool = False) -> None:
    """
    Gracefully shutdown all plugin instances and the global event system.

    Steps:
      1. For each plugin instance in the PluginMeta.cache, call `aclose()` and await completion.
      2. Call `global_async_handler.shutdown(wait=True, timeout=timeout)` to drain pending tasks and shut down the executor.
      3. Optionally clear the PluginMeta.cache.
    """
    logger.info("shutdown_all: starting graceful shutdown; timeout=%s, clear_cache=%s", timeout, clear_cache)

    # 1) gather plugin close coroutines
    to_close: List[Awaitable[Any]] = []
    # snapshot keys to avoid modification during iteration
    keys = list(PluginMeta.cache)
    for key in keys:
        inst = PluginMeta.cache.get(key)
        if inst is None:
            continue
        # call aclose (async) if available
        coro = inst.aclose()
        to_close.append(coro)

    # wait for plugin closures
    if to_close:
        try:
            # wait for all plugin aclose with optional timeout
            tasks = [asyncio.create_task(c) for c in to_close]
            done, pending = await asyncio.wait(tasks, timeout=timeout, return_when=asyncio.ALL_COMPLETED)
            for d in done:
                try:
                    _ = d.result()
                except Exception:
                    logger.exception("shutdown_all: plugin aclose raised")
            for p in pending:
                p.cancel()
        except Exception:
            logger.exception("shutdown_all: error waiting for plugin aclose tasks")

    # 2) shutdown the global handler/dispatcher
    try:
        await global_async_handler.shutdown(wait=True, timeout=timeout)
    except Exception:
        logger.exception("shutdown_all: error shutting down global handler")

    # 3) optional cache clear
    if clear_cache:
        PluginMeta.cache.clear()

    logger.info("shutdown_all: complete")
