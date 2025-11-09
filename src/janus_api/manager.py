# plugin_manager_with_base.py
"""
Plugin manager implementation that uses an abstract PluginBase.

Features
- PluginBase: an ABC that defines lifecycle hooks (setup/start/stop) and a `plugin_id` property.
- PluginManager[P]: a MutableMapping registry bounded to PluginBase (P bound to PluginBase).
- Optional runtime validation (validate_plugin_type) to enforce plugins inherit from PluginBase.
- Default lifecycle handling: on_register calls plugin.setup() and plugin.start(); on_unregister calls plugin.stop().
- Thread-safety (thread_safe=True) using RLock.
- Sync and async lazy registration helpers.

Usage: see the example at the bottom of the file.
"""
from __future__ import annotations

from collections import OrderedDict
from collections.abc import MutableMapping
from typing import (
    TypeVar,
    Generic,
    Iterator,
    Optional,
    Callable,
    Awaitable,
    Any,
)
import threading
import asyncio
import logging

from reactivex import Subject as RxSubject

from janus_api.plugins.base import PluginBase
from janus_api.exceptions import PluginAlreadyRegistered, PluginNotRegistered


# ----------------------
# PluginManager
# ----------------------

P = TypeVar("P", bound=PluginBase)


class PluginManager(Generic[P], MutableMapping):
    """A typed registry for plugins bounded to PluginBase.

    Parameters
    - thread_safe: if True, operations are protected by an RLock.
    - logger: optional logger to use. If None, the module logger is used.
    - validate_plugin_type: if True, enforce isinstance(plugin, PluginBase) at runtime.
    - on_register: optional callback (plugin_id, plugin) called after registration.
      By default it calls plugin.setup() then plugin.start().
    - on_unregister: optional callback (plugin_id, plugin) called when a plugin is removed.
      By default it calls plugin.stop().
    """

    def __init__(self, *, thread_safe: bool = False, logger: Optional[logging.Logger] = None,
                 validate_plugin_type: bool = False, on_register: Optional[Callable[[str | int, P], None]] = None,
                 on_unregister: Optional[Callable[[str | int, P], None]] = None) -> None:
        self._registry: "OrderedDict[str|int, P]" = OrderedDict()
        self._lock: Optional[threading.RLock] = threading.RLock() if thread_safe else None
        self._async_lock: Optional[asyncio.Lock] = None
        self.logger = logger or logging.getLogger(__name__)
        self.validate_plugin_type = validate_plugin_type

        # default lifecycle handlers
        if on_register is None:
            def _default_on_register(plugin_id: str | int, plugin: P) -> None:
                try:
                    plugin.setup()
                except (AttributeError, ValueError):
                    self.logger.exception("plugin.setup() raised for %s", plugin_id)
                try:
                    plugin.start()
                except (AttributeError, ValueError):
                    self.logger.exception("plugin.start() raised for %s", plugin_id)

            self.on_register = _default_on_register
        else:
            self.on_register = on_register

        if on_unregister is None:
            def _default_on_unregister(plugin_id: str|int, plugin: P) -> None:
                try:
                    plugin.stop()
                except Exception:
                    self.logger.exception("plugin.stop() raised for %s", plugin_id)

            self.on_unregister = _default_on_unregister
        else:
            self.on_unregister = on_unregister

    # ----------------------
    # internal helpers
    # ----------------------

    def _acquire(self) -> None:
        if self._lock:
            self._lock.acquire()

    def _release(self) -> None:
        if self._lock:
            self._lock.release()

    def _ensure_async_lock(self) -> asyncio.Lock:
        # created lazily to avoid creating asyncio primitives in sync-only apps
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock

    def _ensure_plugin_type(self, plugin: Any) -> None:
        if self.validate_plugin_type and not isinstance(plugin, PluginBase):
            raise TypeError(f"plugin must inherit from PluginBase; got {type(plugin)!r}")

    # ----------------------
    # MutableMapping protocol
    # ----------------------

    def __getitem__(self, key: str) -> P:
        try:
            return self._registry[key]
        except KeyError as exc:
            raise PluginNotRegistered(f"Plugin '{key}' is not registered.") from exc

    def __setitem__(self, key: str, value: P) -> None:
        self._ensure_plugin_type(value)
        if key in self._registry:
            raise PluginAlreadyRegistered(f"Plugin '{key}' is already registered.")

        # create per-plugin reactive subject (best-effort)
        try:
            if RxSubject is not None:
                subj = RxSubject()
                setattr(value, "_plugin_rx_base", subj)
        except Exception:
            setattr(value, "_plugin_rx_base", None)

        # ensure plugin has emitter (PluginBase already sets one)
        self._registry[key] = value
        try:
            self.on_register(key, value)
        except Exception:
            self.logger.exception("on_register callback raised for %s", key)

    def __delitem__(self, key: str) -> None:
        try:
            plugin = self._registry.pop(key)
        except KeyError as exc:
            raise PluginNotRegistered(f"Plugin '{key}' is not registered.") from exc

        # complete plugin rx subject (best-effort)
        try:
            subj = getattr(plugin, "_plugin_rx_base", None)
            if subj is not None:
                subj.on_completed()
        except Exception:
            pass

        try:
            self.on_unregister(key, plugin)
        except Exception:
            self.logger.exception("on_unregister callback raised for %s", key)

    def __iter__(self) -> Iterator[str|int]:
        return iter(self._registry)

    def __len__(self) -> int:
        return len(self._registry)

    def __contains__(self, name: object) -> bool:  # type: ignore[override]
        return name in self._registry

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(plugins={list(self._registry.keys())})"

    # ----------------------
    # public API
    # ----------------------

    def register(self, plugin_id: str | int, plugin: P, *, force: bool = False) -> None:
        self._ensure_plugin_type(plugin)
        self._acquire()
        try:
            if not force and str(plugin_id) in self._registry:
                raise PluginAlreadyRegistered(f"Plugin '{plugin_id}' already exists.")

            # create per-plugin rx subject if missing (consistent with __setitem__)
            try:
                if getattr(plugin, "_plugin_rx_base", None) is None:
                    setattr(plugin, "_plugin_rx_base", RxSubject())
            except Exception:
                pass

            previous = self._registry.get(plugin_id)
            self._registry[plugin_id] = plugin
            try:
                self.on_register(plugin_id, plugin)
            except Exception:
                self.logger.exception("on_register callback failed for %s", plugin_id)
        finally:
            self._release()

    def unregister(self, plugin_id: str | int) -> P:
        self._acquire()
        try:
            try:
                plugin = self._registry.pop(plugin_id)
            except KeyError as exc:
                raise PluginNotRegistered(f"Plugin '{plugin_id}' is not registered.") from exc
            # complete plugin rx subject
            try:
                subj = getattr(plugin, "_plugin_rx_base", None)
                if subj is not None:
                    subj.on_completed()
            except Exception:
                pass
            try:
                self.on_unregister(plugin_id, plugin)
            except Exception:
                self.logger.exception("on_unregister callback failed for %s", plugin_id)
            return plugin
        finally:
            self._release()

    def clear(self) -> None:
        self._acquire()
        try:
            if self.on_unregister:
                for n, p in list(self._registry.items()):
                    try:
                        # complete rx subject before calling on_unregister
                        try:
                            subj = getattr(p, "_plugin_rx_base", None)
                            if subj is not None:
                                subj.on_completed()
                        except Exception:
                            pass
                        self.on_unregister(n, p)
                    except Exception:
                        self.logger.exception("on_unregister callback failed for %s", n)
            self._registry.clear()
        finally:
            self._release()

    def get(self, plugin_id: str, default: Optional[P] = None) -> Optional[P]:
        """Like dict.get — return plugin if present else default."""
        return self._registry.get(plugin_id, default)

    def register_if_missing(self, plugin_id: str, factory: Callable[[], P]) -> P:
        self._acquire()
        try:
            if plugin_id in self._registry:
                return self._registry[plugin_id]
            plugin = factory()
            self._ensure_plugin_type(plugin)
            # create plugin rx subject
            try:
                if RxSubject is not None and getattr(plugin, "_plugin_rx_base", None) is None:
                    setattr(plugin, "_plugin_rx_base", RxSubject())
            except Exception:
                setattr(plugin, "_plugin_rx_base", None)
            self._registry[plugin_id] = plugin
            try:
                self.on_register(plugin_id, plugin)
            except Exception:
                self.logger.exception("on_register callback failed for %s", plugin_id)
            return plugin
        finally:
            self._release()

    async def async_register_if_missing(self, handle_id: str, async_factory: Callable[[], Awaitable[P]]) -> P:
        lock = self._ensure_async_lock()
        async with lock:
            if handle_id in self._registry:
                return self._registry[handle_id]
            plugin = await async_factory()
            self._ensure_plugin_type(plugin)
            # create plugin rx subject
            try:
                if RxSubject is not None and getattr(plugin, "_plugin_rx_base", None) is None:
                    setattr(plugin, "_plugin_rx_base", RxSubject())
            except Exception:
                setattr(plugin, "_plugin_rx_base", None)
            self._acquire()
            try:
                self._registry[handle_id] = plugin
            finally:
                self._release()
            try:
                self.on_register(handle_id, plugin)
            except Exception:
                self.logger.exception("on_register callback failed for %s", handle_id)
            return plugin

    def register_or_replace(self, handle_id: str, plugin: P) -> Optional[P]:
        self._ensure_plugin_type(plugin)
        self._acquire()
        try:
            previous = self._registry.get(handle_id)
            # create rx subject for new plugin
            try:
                if RxSubject is not None and getattr(plugin, "_plugin_rx_base", None) is None:
                    setattr(plugin, "_plugin_rx_base", RxSubject())
            except Exception:
                setattr(plugin, "_plugin_rx_base", None)
            self._registry[handle_id] = plugin
            try:
                self.on_register(handle_id, plugin)
            except Exception:
                self.logger.exception("on_register callback failed for %s", handle_id)
            return previous
        finally:
            self._release()

    def as_dict(self) -> dict:
        """Shallow copy as a plain dict preserving insertion order."""
        return dict(self._registry)

    def dispatch(self, handle_id: str|int, evt) -> None:
        """
        Deliver evt to single plugin (by handle_id). Best-effort:
         - call plugin.on_event (sync or coroutine)
         - push evt to plugin._plugin_rx_base.on_next(...)
         - emit on plugin.emitter.emit("event", evt)
         - if plugin is a bare callable, call it
        """
        plugin = self._registry.get(handle_id)
        if plugin is None:
            raise PluginNotRegistered(f"Plugin '{handle_id}' is not registered.")

        # 1) on_event
        try:
            handler = getattr(plugin, "on_event", None)
            if callable(handler):
                r = handler(evt)
                if asyncio.iscoroutine(r):
                    asyncio.create_task(r)
        except Exception:
            self.logger.exception("plugin on_event raised for %s", handle_id)

        # 2) reactive subject push
        try:
            subj = getattr(plugin, "_plugin_rx_base", None)
            if subj is not None:
                try:
                    subj.on_next(evt)
                except Exception:
                    # swallow but log
                    self.logger.exception("failed to push to plugin rx subject for %s", handle_id)
        except Exception:
            self.logger.exception("plugin rx dispatch error for %s", handle_id)

        # 3) emitter
        try:
            em = getattr(plugin, "emitter", None)
            if em is not None:
                try:
                    em.emit("event", evt)
                except Exception:
                    self.logger.exception("failed to emit to plugin emitter for %s", handle_id)
        except Exception:
            self.logger.exception("plugin emitter dispatch failed for %s", handle_id)


# ----------------------
# Example usage
# ----------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    class CachePlugin(PluginBase):
        def __init__(self, name: str, size: int = 128) -> None:
            self._name = name
            self.size = size
            self.started = False

        @property
        def name(self) -> str:
            return self._name

        def setup(self) -> None:
            print(f"{self.name}: setup (size={self.size})")

        def start(self) -> None:
            self.started = True
            print(f"{self.name}: started")

        def stop(self) -> None:
            self.started = False
            print(f"{self.name}: stopped")

    pm = PluginManager[PluginBase](thread_safe=True, validate_plugin_type=True)

    cache = CachePlugin("cache", size=256)
    pm.register("cache", cache)

    print(pm)

    # lazy creation example
    def make_logger_plugin() -> CachePlugin:
        return CachePlugin("logger", size=32)

    logger_plugin = pm.register_if_missing("logger", make_logger_plugin)
    print("logger started?", logger_plugin.started)

    # unregister
    removed = pm.unregister("cache")
    print("removed", removed)

    # async lazy registration demo
    async def async_demo():
        async def async_factory() -> CachePlugin:
            await asyncio.sleep(0.01)
            return CachePlugin("remote", size=16)

        remote = await pm.async_register_if_missing("remote", async_factory)
        print("remote registered:", remote)

    asyncio.run(async_demo())

# End of file
