from __future__ import annotations

import asyncio
import functools
import inspect
import logging
from concurrent.futures import ThreadPoolExecutor, Future as CFuture
from typing import (
    Any,
    Awaitable,
    Callable,
    List,
    Optional,
    Sequence,
    Set,
    Union,
)

logger = logging.getLogger(__name__)

# ---------------------------
# Type aliases
# ---------------------------
Listener = Callable[..., Union[Awaitable[Any], Any]]


# ---------------------------
# Async Dispatcher with pending-task tracking & graceful shutdown
# ---------------------------
class AsyncDispatcher:
    def __init__(
            self,
            *,
            run_sync_in_executor: bool = True,
            max_workers: Optional[int] = 8,
            executor: Optional[ThreadPoolExecutor] = None,
    ) -> None:
        self.run_sync_in_executor = bool(run_sync_in_executor)
        self._executor = executor or (ThreadPoolExecutor(max_workers=max_workers) if run_sync_in_executor else None)
        # track pending asyncio.Future/Task objects
        self._pending: Set[asyncio.Future] = set()
        self._pending_lock = asyncio.Lock()

    async def dispatch_single(
            self,
            callback: Listener,
            *args: Any,
            timeout: Optional[float] = None,
            wait: bool = False,
            **kwargs: Any,
    ) -> List[asyncio.Future]:
        loop = asyncio.get_running_loop()
        is_coro = inspect.iscoroutinefunction(callback)

        if is_coro:
            coro = callback(*args, **kwargs)  # type: ignore[call-arg]
            task = loop.create_task(self._wrap_coro(coro, callback))
            self._track(task)
            if wait:
                results = await self._await_all([task], timeout)
                return [asyncio.get_event_loop().create_future()] if False else [task]
            return [task]

        # sync callable -> run in executor and wrap
        if self.run_sync_in_executor and self._executor is not None:
            cf_future: CFuture = loop.run_in_executor(self._executor,
                                                      functools.partial(self._wrap_sync, callback, *args, **kwargs))
            # wrap concurrent.futures.Future into asyncio.Future tied to the running loop
            async_fut: asyncio.Future = asyncio.wrap_future(cf_future, loop=loop)
            self._track(async_fut)
            if wait:
                results = await self._await_all([async_fut], timeout)
                return [async_fut]
            return [async_fut]

        # fallback: call sync directly on loop (not recommended)
        try:
            result = callback(*args, **kwargs)
            fut = loop.create_future()
            fut.set_result(result)
            # track and return
            self._track(fut)
            if wait:
                return [fut]
            return [fut]
        except Exception as exc:
            logger.exception("Dispatcher: sync callback %r raised", callback)
            fut = loop.create_future()
            fut.set_exception(exc)
            self._track(fut)
            return [fut]

    def _track(self, future: asyncio.Future) -> None:
        # add to pending and ensure removal when done
        async def _add():
            async with self._pending_lock:
                self._pending.add(future)
            # remove on done
            future.add_done_callback(lambda f: asyncio.get_event_loop().call_soon_threadsafe(self._remove_done, f))

        # schedule the _add into loop
        try:
            loop = asyncio.get_running_loop()
            # if we are here, schedule _add immediately
            loop.call_soon_threadsafe(asyncio.create_task, _add())
        except RuntimeError:
            # not in running loop: best-effort sync add (rare)
            # use threading to add to pending (not ideal)
            # but we'll simply add without lock if loop isn't running
            self._pending.add(future)
            future.add_done_callback(lambda f: self._remove_done(f))

    def _remove_done(self, future: asyncio.Future) -> None:
        # called in event loop thread via call_soon_threadsafe
        try:
            # safe discard
            self._pending.discard(future)
        except Exception:
            logger.exception("Dispatcher: error removing done future from pending")

    async def _await_all(self, tasks: Sequence[Awaitable[Any]], timeout: Optional[float]) -> List[Any]:
        tasks_list = [asyncio.ensure_future(t) for t in tasks]
        try:
            done, pending = await asyncio.wait(tasks_list, timeout=timeout, return_when=asyncio.ALL_COMPLETED)
            results: List[Any] = []
            for t in done:
                results.append(t.result())
            for p in pending:
                p.cancel()
            return results
        except Exception:
            logger.exception("Dispatcher: error awaiting tasks")
            for t in tasks_list:
                if not t.done():
                    t.cancel()
            raise

    async def _wrap_coro(self, coro: Awaitable[Any], callback: Listener) -> Any:
        try:
            return await coro
        except Exception:
            logger.exception("Dispatcher: coroutine listener %r raised", callback)
            raise

    def _wrap_sync(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception:
            logger.exception("Dispatcher: sync listener %r raised", fn)
            raise

    async def shutdown(self, wait: bool = True, timeout: Optional[float] = None) -> None:
        """
        Graceful shutdown:
        - If wait=True: await completion of pending tasks up to `timeout` seconds, then cancel remaining.
        - Always attempts to shutdown the executor (non-blocking).
        """
        logger.info("AsyncDispatcher: shutdown(wait=%s, timeout=%s)", wait, timeout)
        # snapshot pending futures
        async with self._pending_lock:
            pending = list(self._pending)
        if wait and pending:
            try:
                # await completion with timeout
                done, pending2 = await asyncio.wait(pending, timeout=timeout, return_when=asyncio.ALL_COMPLETED)
                # log exceptions in done
                for d in done:
                    try:
                        _ = d.result()
                    except Exception:
                        logger.exception("AsyncDispatcher: listener raised during shutdown")
                # cancel left-over tasks
                for p in pending2:
                    p.cancel()
            except Exception:
                logger.exception("AsyncDispatcher: error waiting for pending tasks during shutdown")
                for p in pending:
                    if not p.done():
                        p.cancel()
        else:
            # not waiting -> cancel all pending
            for p in pending:
                if not p.done():
                    p.cancel()

        # attempt to shutdown executor
        if self._executor:
            try:
                self._executor.shutdown(wait=False)
            except Exception:
                logger.exception("AsyncDispatcher: executor shutdown error")

        # clear pending set
        async with self._pending_lock:
            self._pending.clear()


# default dispatcher
default_async_dispatcher = AsyncDispatcher()