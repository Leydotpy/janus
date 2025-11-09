"""Plugin base classes and registry adapted to the session/transport design.

Intentions preserved from your original code:
- dynamic plugin discovery/registration
- factory-style plugin instantiation by 'type' or 'variant'
- PluginBase that wraps send/attach/detach and exposes a default `on_event` handler
"""
import asyncio
import importlib
import logging
import pkgutil
from typing import AnyStr, Type, Dict, Optional, TypedDict, Unpack, Callable, Any, Self, Literal, overload, \
    TYPE_CHECKING, Union

from pyee.asyncio import AsyncIOEventEmitter

from janus_api.models.base import Jsep
from janus_api.models.request import PluginMessageRequest, PluginRequestBody, TrickleCandidate
from janus_api.models.response import JanusResponse
from janus_api.session.base import AbstractBaseSession

if TYPE_CHECKING:
    from janus_api.plugins.videoroom import Publisher, Subscriber
    from janus_api.plugins.textroom import TextRoomPlugin
    from janus_api.plugins.audiobridge import Audiobridge
    from janus_api.plugins.p2p import PeerToPeerPlugin
    from janus_api.plugins.sip import SipPlugin
    from janus_api.plugins.streaming import StreamingPlugin

logger = logging.getLogger("janus.plugins")


class PluginKwargs(TypedDict, total=False):
    plugin_id: str | int
    session: Optional[AbstractBaseSession]
    on_event: Callable[[JanusResponse], Any]
    on_rx_event: Callable[[JanusResponse], Any]
    room: Optional[str | int]
    username: Optional[str]
    mode: Optional[str]
    type: Literal["videoroom", "textroom", "audiobridge", "p2p", "sip", "streaming"]


class PluginRegistry:
    """Simple registry for plugin classes keyed by short plugin_id (e.g. 'videoroom')."""

    _registry: Dict[str, Type[Any]] = {}
    ready = False

    @classmethod
    def register(cls, *, name: str):
        def _decorator[T](plugin_cls: Type[T]) -> T:
            cls._registry[name] = plugin_cls
            plugin_cls._variant_type = plugin_cls
            return plugin_cls

        return _decorator

    @classmethod
    def get(cls, name: str):
        return cls._registry.get(name)

    @classmethod
    def pop(cls, name: str):
        return cls._registry.pop(name)

    @classmethod
    def load(cls, package_path: str = "janus_api.plugins") -> None:
        if cls.ready:
            return
        try:
            module = importlib.import_module(package_path)
        except Exception as e:
            logger.exception("failed to import plugins package %s: %s", package_path, e)
            raise
        for finder, name, ispkg in pkgutil.iter_modules(module.__path__):
            if name == "base":
                continue
            importlib.import_module(f"{package_path}.{name}")
        cls.ready = True

    @classmethod
    def items(cls):
        return cls._registry.items()


class PluginMeta(type):
    """Metaclass that ensures plugins are discovered and allows Plugin(...) factory semantics.

    Usage: Plugin(type='videoroom', session=...) -> returns instance of registered plugin
    """

    @overload
    def __call__(
            cls,
            *,
            type: Literal["audiobridge"],
            mode: Optional[str],
            **kwargs: Unpack[PluginKwargs]
    ) -> "Audiobridge":
        ...

    @overload
    def __call__(
            cls,
            *,
            type: Literal["textroom"],
            mode: Optional[str],
            **kwargs: Unpack[PluginKwargs]
    ) -> "TextRoomPlugin":
        ...

    @overload
    def __call__(
            cls,
            *,
            type: Literal["p2p"],
            mode: Optional[str],
            **kwargs: Unpack[PluginKwargs]
    ) -> "PeerToPeerPlugin":
        ...

    @overload
    def __call__(
            cls,
            *,
            type: Literal["sip"],
            mode: Optional[str],
            **kwargs: Unpack[PluginKwargs]
    ) -> "SipPlugin":
        ...

    @overload
    def __call__(
            cls,
            *,
            type: Literal["streaming"],
            mode: Optional[str],
            **kwargs: Unpack[PluginKwargs]
    ) -> "StreamingPlugin":
        ...

    @overload
    def __call__(
            cls,
            *,
            type: Literal["videoroom"],
            mode: Optional[Literal["publisher"]],
            **kwargs: Unpack[PluginKwargs]
    ) -> "Publisher":
        ...

    @overload
    def __call__(
            cls,
            *,
            type: Literal["videoroom"],
            mode: Optional[Literal["subscriber"]],
            **kwargs: Unpack[PluginKwargs]
    ) -> "Subscriber":
        ...

    @overload
    def __call__(
            cls,
            *,
            type: str,
            mode: Optional[str],
            **kwargs: Unpack[PluginKwargs]
    ) -> Union[
        "PluginBase", "TextRoomPlugin", "Publisher", "Subscriber", "PeerToPeerPlugin", "SipPlugin", "StreamingPlugin", "Audiobridge",]:
        ...

    def __call__(
            cls,
            *,
            type: str,
            mode: Optional[str],
            **kwargs: Unpack[PluginKwargs]
    ):
        if mode is not None:
            kwargs["mode"] = mode
        if not type:
            # direct instantiation of a concrete subclass
            return super().__call__(**kwargs)
        target = PluginRegistry.get(type)
        if target is not None:
            return target(**kwargs)
        raise ValueError(f"No registered plugin variant: {type}")


class Plugin(metaclass=PluginMeta):
    name = None

    def __init__(self, **kwargs: Unpack[PluginKwargs]):
        raise NotImplemented

    @overload
    @classmethod
    async def attach(
            cls,
            *,
            type: Literal["audiobridge"],
            mode: Optional[str],
            **kwargs: Unpack[PluginKwargs]
    ) -> "Audiobridge": ...

    @overload
    @classmethod
    async def attach(
            cls,
            *,
            type: Literal["p2p"],
            mode: Optional[str],
            **kwargs: Unpack[PluginKwargs]
    ) -> "PeerToPeerPlugin": ...

    @overload
    @classmethod
    async def attach(
            cls,
            *,
            type: Literal["streaming"],
            mode: Optional[str],
            **kwargs: Unpack[PluginKwargs]
    ) -> "StreamingPlugin": ...

    @overload
    @classmethod
    async def attach(
            cls,
            *,
            type: Literal["videoroom"],
            mode: Optional[Literal["publisher"]],
            **kwargs: Unpack[PluginKwargs]
    ) -> "Publisher": ...

    @overload
    @classmethod
    async def attach(
            cls,
            *,
            type: Literal["videoroom"],
            mode: Optional[Literal["subscriber"]],
            **kwargs: Unpack[PluginKwargs]
    ) -> "Subscriber": ...

    @overload
    @classmethod
    async def attach(
            cls,
            *,
            type: Literal["textroom"],
            mode: Optional[str],
            **kwargs: Unpack[PluginKwargs]
    ) -> "TextRoomPlugin": ...

    @overload
    @classmethod
    async def attach(
            cls,
            *,
            type,
            mode: Optional[str],
            **kwargs: Unpack[PluginKwargs]
    ) -> Union[
        "PluginBase", "TextRoomPlugin", "Publisher", "Subscriber", "PeerToPeerPlugin", "SipPlugin", "StreamingPlugin", "Audiobridge",]: ...

    @classmethod
    async def attach(
            cls,
            *,
            type,
            mode: Optional[str],
            **kwargs: Unpack[PluginKwargs]
    ):
        subclass = cls(type=type, mode=mode, **kwargs)
        plugin = await subclass.attach()
        return plugin


class PluginBase:
    """Base class for concrete plugin implementations.

    Concrete plugin classes should set `plugin_id = "janus.plugin.*"` and implement API helper methods
    as needed. The base provides `send` helper and `on_event` default handler.
    """

    name: Optional[str] = None  # e.g. "janus.plugin.videoroom"
    # class-level session (set in AbstractBaseSession._setup for convenience)
    __session__: Optional[AbstractBaseSession] = None
    __slots__ = (
        "__plugin_id",
        "__session",
        "__plugin_emitter",
        "__plugin_rx_base",
        "__rx_dispose",
        "__on_rx_event",
        "__on_event",
    )

    def __init__(
            self,
            *,
            plugin_id: Optional[str | int] = None,
            session: Optional[AbstractBaseSession] = None,
            on_event: Callable[[JanusResponse], Any] = None,
            on_rx_event: Callable[[JanusResponse], Any] = None,
            **kwargs: Unpack[PluginKwargs]
    ):
        self.__plugin_id = plugin_id
        # Prefer instance session argument; fall back to class-level __session__ if present
        self.__session = session or getattr(self.__class__, "__session__", None)
        if self.__session is None:
            raise RuntimeError("Plugin must be created with an associated session or have a class __session__ set")

        # create a per-plugin emitter (pyee) for event-style APIs

        self.__plugin_emitter = AsyncIOEventEmitter()

        # _plugin_rx_base will be set by PluginManager.register (best-effort)
        self.__plugin_rx_base = None
        self.__rx_dispose = None
        self.__on_rx_event = None

        # Default event handler called by session routing through the PluginManager when a plugin event arrives.
        # these callbacks should be passed to the plugin to implement plugin-specific logic.
        if on_event is None:
            def _default_on_event(evt: JanusResponse) -> None:
                # by default just log
                logger.debug("Plugin %s received event: %s", getattr(self, "id", None), evt)

            self.__on_event = _default_on_event
        else:
            self.__on_event = on_event
        if on_rx_event is None:
            def _default_on_rx_event(evt: JanusResponse) -> None:
                # reactivex callbacks
                logger.info("rx event: %s", evt)

            self.__on_rx_event = _default_on_rx_event
        else:
            self.__on_rx_event = on_rx_event

    @property
    def id(self) -> str:
        return self.__plugin_id  # type: ignore

    @id.setter
    def id(self, value: AnyStr):
        self.__plugin_id = value

    @property
    def session(self) -> AbstractBaseSession:
        if not self.__session:
            raise RuntimeError("Plugin has no associated session")
        return self.__session

    def setup(self):
        # subscribe to plugin-level reactive subject delivered by PluginManager
        dispose = self.subscribe_rx(self.__on_rx_event)
        self.__rx_dispose = dispose
        # if you want event-based handling optionally
        if self.emitter:
            self.emitter.on("event", lambda e: self.__on_event(e))

    def start(self):
        # connect the global/transport connectable so that rx streams start flowing
        # (session.transport.connect_reactive is asynchronous)
        asyncio.create_task(self.session.transport.connect_reactive())

    def stop(self):
        try:
            self.__rx_dispose()
        except Exception as e:
            logger.exception(e)

        try:
            asyncio.create_task(self.session.transport.disconnect_reactive())
        except Exception as e:
            logger.exception(e)

    @property
    def emitter(self):
        return self.__plugin_emitter

    @property
    def rx(self):
        return self.__plugin_rx_base

    def subscribe_rx(self, callback):
        """Subscribe callback to plugin-level reactive stream (if available). Returns disposable or None."""
        subj = getattr(self, "__plugin_rx_base", None)
        if subj is None:
            return None
        try:
            return subj.subscribe(callback)
        except Exception:
            return None

    def emit_plugin_event(self, name: str, payload):
        if getattr(self, "__plugin_emitter", None) is not None:
            try:
                self.__plugin_emitter.emit(name, payload)
            except Exception:
                logger.exception("plugin emitter failed during emit")

    async def attach(self) -> Self:
        self.id = await self.session.attach(str(self.__class__.name))
        # register in session-wide plugin manager if supported
        try:
            self.session.plugins.register(self.id, self)
        except Exception as e:
            logger.exception("Failed to register plugin with handle id '%s'.", self.id, exc_info=e)
            pass
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

        body = TrickleMessageRequest(janus="trickle", session_id=str(self.session.id), handle_id=self.id,
                                     candidates=candidates, )
        return await self.session.send(body)
