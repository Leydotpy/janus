from __future__ import annotations

import asyncio
import logging
import threading
from typing import (
    Any,
    Awaitable,
    Callable,
    List,
    Optional,
    Type,
    TypeVar,
    Union, TypedDict, Required, Unpack, Self, TYPE_CHECKING,
)

from reactivex import Subject
from reactivex.abc import DisposableBase

from janus_api.models import JanusResponse
from janus_api.models.base import Jsep
from janus_api.models.request import PluginRequestBody, PluginMessageRequest, TrickleCandidate
from janus_api.models.response import WebRTCEvent
from janus_api.lib.cache import Cache
from janus_api.lib.events.emitter import AsyncEmitter
from janus_api.lib.events.handler import AsyncEventHandler, global_async_handler
from janus_api.lib.registry import Registry

if TYPE_CHECKING:
    from janus_api.session.base import AbstractBaseSession

logger = logging.getLogger(__name__)

# ---------------------------
# Type aliases
# ---------------------------
Listener = Callable[..., Union[Awaitable[Any], Any]]

K = TypeVar("K")
V = TypeVar("V")
TPlugin = TypeVar("TPlugin", bound="Plugin")


class PluginOptions(TypedDict, total=False):
    identifier: Required[str]
    plugin_id: Optional[str | int]
    session: Optional[AbstractBaseSession]
    on_event: Callable[[JanusResponse], Any]
    on_rx_event: Callable[[JanusResponse], Any]


# ---------------------------
# Plugin Meta + Plugin (with async shutdown support)
# ---------------------------
class PluginMeta(type):
    registry: Registry["Plugin"] = Registry()
    cache: Cache[str, "Plugin"] = Cache(max_size=4096, ttl=None)
    _lock = threading.RLock()

    def __call__(cls: Type[TPlugin], *args: Any, **kwargs: Unpack[PluginOptions]) -> TPlugin:
        plugin_id = kwargs.get("plugin_id", None)
        with PluginMeta._lock:
            if plugin_id is not None:
                inst = PluginMeta.cache.get(plugin_id)  # type: ignore[arg-type]
                if inst is not None and isinstance(inst, cls):
                    logger.debug("PluginMeta: returning cached %r for plugin_id=%r", cls.__name__, plugin_id)
                    return inst  # type: ignore[return-value]
            instance = super().__call__(*args, **kwargs)  # type: ignore[arg-type]
            if plugin_id is not None:
                PluginMeta.cache[plugin_id] = instance  # type: ignore[assignment]
            return instance  # type: ignore[return-value]


class Plugin(metaclass=PluginMeta):
    identifier: Optional[str] = None
    name: Optional[str] = None
    event_handler: AsyncEventHandler = global_async_handler

    __slots__ = (
        "_plugin_id",
        "_session",
        "_emitter",
        "_rx_base",
        "_rx_dispose",
        "_on_rx_event",
        "_on_event",
    )

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        ident = getattr(cls, "identifier", None)
        if ident:
            PluginMeta.registry.register(ident, cls)  # type: ignore[arg-type]
            logger.info("Plugin: registered %s as %r", cls.__name__, ident)

    def __init__(self, *, plugin_id: Optional[str] = None, **kwargs: Unpack[PluginOptions]) -> None:
        self._plugin_id = plugin_id
        self._session = kwargs.get("session", None)
        if self._session is None:
            raise RuntimeError(
                """
                Plugin must be instantiated with an associated session.
                please make sure that the global session is set or manually pass the session instance during instantiation.
                """
            )

        ns = getattr(self, "identifier", self.__class__.__name__)
        self._emitter = AsyncEmitter(self.event_handler, namespace=ns)
        self._rx_base: Optional[Subject] = None
        self._rx_dispose: Optional[DisposableBase] = None

        def _default_on_event(evt: WebRTCEvent | Jsep) -> None:
            # by default just log
            logger.debug("Plugin %s received event: %s", getattr(self, "id", None), evt)

        def _default_on_rx_event(evt: WebRTCEvent | Jsep) -> None:
            # reactivex callbacks
            logger.info("rx event: %s", evt)

        self._on_rx_event = kwargs.get("on_rx_event", _default_on_rx_event)
        self._on_event = kwargs.get("on_event", _default_on_event)

    def __new__(cls, *args, **kwargs: Unpack[PluginOptions]):
        identifier = kwargs.get("identifier", None)
        if not identifier:
            raise AttributeError("plugin identifier is required")
        plugin_cls = PluginMeta.registry.get(str(identifier))
        if not plugin_cls:
            raise KeyError(f"No plugin registered with identifier {identifier!r}")
        return object.__new__(plugin_cls)

    @classmethod
    def list_registered(cls) -> List[str]:
        return list(PluginMeta.registry)

    async def on(self, event: str, callback: Listener) -> None:
        full_event = f"{self.identifier or self.__class__.__name__}.{event}"
        await self.event_handler.add_listener(full_event, callback)

    async def emit(self, event: str, *args: Any, wait: bool = False, timeout: Optional[float] = None, **kwargs: Any) -> \
            List[Any]:
        return await self.emitter.emit(event, *args, wait=wait, timeout=timeout, **kwargs)

    def subscribe_rx(self, callback) -> DisposableBase | None:
        """Subscribe callback to plugin-level reactive stream (if available). Returns disposable or None."""
        subj = self.rx
        if subj is None:
            return None
        try:
            return subj.subscribe(callback)
        except Exception:
            return None

    def start(self):
        # Transport events are emitted on a hot subject, so plugin startup only needs
        # the per-plugin subscription established in setup().
        return None

    def stop(self):
        dispose = self._rx_dispose
        if dispose is not None:
            try:
                if hasattr(dispose, "dispose"):
                    dispose.dispose()
                elif callable(dispose):
                    dispose()
            except Exception as e:
                logger.exception(e)
            finally:
                self._rx_dispose = None

        try:
            asyncio.create_task(self._aclose())
        except Exception as e:
            logger.exception(e)

    def setup(self):
        # subscribe to plugin-level reactive subject delivered by PluginManager
        dispose = self.subscribe_rx(self._on_rx_event)
        self._rx_dispose = dispose
        # if you want event-based handling optionally
        if self.emitter:
            asyncio.create_task(self.on("event", lambda e: self._on_event(e)))

    # sync shutdown hook
    def _shutdown(self) -> None:
        logger.info("Plugin(%s): shutdown called (sync)", self.id)

    # async shutdown hook: override in subclasses if they need async cleanup
    async def _aclose(self) -> None:
        """Optional async cleanup; default calls sync shutdown in executor to avoid blocking loop."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._shutdown)

    async def attach(self) -> Self:
        self.id = await self.session.attach(str(self.__class__.name))
        # register in session-wide plugin manager if supported
        try:
            self.session.plugins.register(self.id, self)
        except Exception as e:
            logger.exception("Failed to register plugin with handle id '%s'.", self.id, exc_info=e)
        return self

    async def detach(self):
        if not self.id:
            raise RuntimeError("Plugin not attached")
        return await self.session.detach(self.id)

    async def send(self, body: PluginRequestBody, jsep: Optional[Jsep] = None):
        if not self.id:
            raise RuntimeError("Plugin must be attached before sending messages")
        message = PluginMessageRequest(janus="message", session_id=self.session.id, handle_id=self.id, body=body,
                                       jsep=jsep, )
        resp = await self.session.send(message)
        return resp

    # Convenience methods that concrete plugin implementations will commonly implement
    async def trickle(self, candidates: list[TrickleCandidate]) -> JanusResponse:
        from janus_api.models.request import TrickleMessageRequest

        body = TrickleMessageRequest(janus="trickle", session_id=self.session.id, handle_id=self.id,
                                     candidates=candidates, )
        return await self.session.send(body)

    @property
    def emitter(self):
        return self._emitter

    @property
    def id(self) -> int:
        if not self._plugin_id:
            raise RuntimeError("Plugin has not been attached yet")
        return int(self._plugin_id)

    @id.setter
    def id(self, plugin_id: str):
        self._plugin_id = plugin_id

    @property
    def session(self) -> AbstractBaseSession:
        if not self._session:
            raise RuntimeError("Plugin has no associated session")
        return self._session

    @property
    def rx(self) -> Subject | None:
        return self._rx_base

    def _set_rx_subject(self, subject: Subject | None) -> None:
        self._rx_base = subject
