"""SessionMeta and AbstractBaseSession with reactive helpers.

This copy is adapted to use create_socket_client above as the transport factory when the
session URL uses ws:// or wss://.
"""
import threading
from typing import AnyStr, Any, Union, Dict, List, Optional

import pyee.asyncio
from decouple import config

from janus_api.manager import PluginManager
from janus_api.models import JanusRequest
from janus_api.models.request import AttachPluginRequest, DetachPluginRequest
from janus_api.transport.websocket import WebsocketTransportClient
from janus_api.transport.websocket import create_socket_client, logger

JANUS_SESSION_URL = config("JANUS_SESSION_URL", default="ws://localhost:8188/janus")


async def create_transport(url: AnyStr) -> Any:
    # returns either WebsocketTransportClient (for ws/wss) or another transport (httpx) if needed
    if url.startswith("ws://") or url.startswith("wss://"):
        return await create_socket_client(url, enable_reactive=True)
    # fallback: httpx AsyncClient could be returned here
    import httpx
    return httpx.AsyncClient(base_url=url)


# -------------------------
# SessionMeta
# -------------------------
class SessionMeta(type):
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def __prepare__(metacls, name, bases, **kwargs):
        namespace = super(SessionMeta, metacls).__prepare__(name, bases, **kwargs)
        # placeholders - adapt to your settings
        namespace["__session_url__"] = globals().get("JANUS_SESSION_URL", None)
        # create_transport should be your factory that yields a transport instance (async)
        namespace["__transport__"] = globals().get("create_transport", None)
        namespace["__plugins__"] = globals().get("PluginManager",
                                                 lambda: None)()  # keep external plugin manager usage intact
        return namespace

    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__call__(*args, **kwargs)
            return cls._instance


# -------------------------
# AbstractBaseSession
# -------------------------
class AbstractBaseSession(metaclass=SessionMeta):
    __slots__ = ("__session_id", "__events", "__transport", "_plugin_subscription_guard", "_plugins_by_handle",
                 "_plugins_by_name", "_rx_subscription",)

    def __init__(self, *, session_id=None):
        self.__session_id: Optional[Union[str, int]] = session_id
        self.__events = pyee.asyncio.AsyncIOEventEmitter() if pyee is not None else None
        self.__transport = None
        self._plugin_subscription_guard = False
        self._plugins_by_handle: Dict[Any, Any] = {}
        self._plugins_by_name: Dict[str, List[Any]] = {}
        self._rx_subscription = None

    @property
    def id(self) -> Union[str, int]:
        return self.__session_id  # type: ignore

    @id.setter
    def id(self, value):
        self.__session_id = value

    @property
    def plugins(self) -> PluginManager:
        return getattr(self.__class__, "__plugins__")

    @property
    def events(self):
        return self.__events

    @property
    def transport(self) -> WebsocketTransportClient:
        return self.__transport

    async def send(self, data: JanusRequest):
        return await self.transport.send(data)

    async def attach(self, plugin: AnyStr):
        if not self.__session_id:
            raise ValueError("Session ID is not set. Cannot attach plugin.")
        message = AttachPluginRequest(janus="attach", plugin=plugin, session_id=self.id)
        response = await self.send(message)
        assert response.janus == "success"
        plugin_id = response.data.id
        return plugin_id

    async def detach(self, handle_id):
        message = DetachPluginRequest(janus="detach", session_id=self.id, handle_id=handle_id)
        response = await self.send(message)
        assert response.janus == "success"
        try:
            del self.plugins[handle_id]
        except Exception:
            pass
        try:
            self._plugins_by_handle.pop(handle_id, None)
        except Exception:
            pass
        try:
            for name, lst in list(self._plugins_by_name.items()):
                self._plugins_by_name[name] = [p for p in lst if getattr(p, "id", None) != handle_id]
                if not self._plugins_by_name[name]:
                    del self._plugins_by_name[name]
        except Exception:
            pass
        return handle_id

    async def create(self):
        raise NotImplementedError()

    async def destroy(self, **kwargs):
        self.plugins.clear()
        if self.transport:
            # remove pyee listeners
            try:
                if self.transport.event is not None:
                    self.transport.event.remove_all_listeners()
            except Exception:
                pass
            # dispose session-level reactive subscription if present
            try:
                sub = getattr(self, "_rx_subscription", None)
                if sub is not None:
                    try:
                        if hasattr(sub, "dispose"):
                            sub.dispose()
                        elif hasattr(sub, "close"):
                            sub.close()
                        else:
                            try:
                                sub()
                            except Exception:
                                pass
                    except Exception:
                        logger.exception("Failed to dispose rx subscription")
                    finally:
                        self._rx_subscription = None
            except Exception:
                logger.exception("Failed while cleaning up rx subscription")
            # transport.stop will close reactive subject if present
            await self.transport.stop()

    async def _setup(self):
        """set up the connection to the websocket server
        called in the .create() method.
        """
        if self.transport and self.transport.open:
            return
        if self.id:
            return
        cls = self.__class__
        session_url = getattr(cls, "__session_url__", None)
        if session_url is None:
            raise ValueError("session_url must be set in settings.py")
        transport_factory = getattr(cls, "__transport__", None)
        if transport_factory is None:
            raise RuntimeError("transport factory not configured")
        self.__transport = await transport_factory(session_url)
        # bind transport emitter events to session events (existing emitter path)
        try:
            if self.__transport.event is not None and self.__events is not None:
                self.__transport.event.on("event", lambda evt: self.__events.emit("event", evt))
        except Exception:
            logger.exception("Failed to bind transport.event to session events")
        # Auto-wire PluginBase.__session__ so plugin classes can be instantiated without passing session
        try:
            from janus_api.plugins.base import PluginBase as JanusPluginBase  # optional, best-effort
            JanusPluginBase.__session__ = self
        except Exception:
            logger.debug("Could not set PluginBase.__session__ (plugins.base import failed)")
        # Auto-wire PluginManager routing: use session._plugins_by_handle, plugin manager, etc.
        if not self._plugin_subscription_guard:
            def _route_event(evt):
                try:
                    plugin_name = getattr(evt, "plugin", None)
                    sender = getattr(evt, "from", None)
                    payload = getattr(evt, "payload")
                    pm = self.plugins

                    # PluginManager dispatch
                    if sender and hasattr(pm, "dispatch"):
                        try:
                            pm.dispatch(str(sender), payload)
                            return
                        except Exception:
                            logger.exception("PluginManager.dispatch failed for %s", plugin_name)
                except Exception:
                    logger.exception("Error routing plugin event")

            # bind emitter-based routing
            try:
                if self.__transport.event is not None:
                    self.__transport.event.on("event", _route_event)
            except Exception:
                logger.exception("Failed to bind emitter-based plugin routing")
            # --- reactive subscription: route connectable stream to same _route_event ---
            try:
                rx_conn = getattr(self.__transport, "reactive", None)
                if rx_conn is not None:
                    def _rx_on_next(payload):
                        try:
                            _route_event(payload)
                        except Exception:
                            logger.exception("Error routing event from reactive stream")

                    try:
                        self._rx_subscription = rx_conn.subscribe(_rx_on_next)
                    except Exception:
                        try:
                            class _Observer:
                                def on_next(self, v): _rx_on_next(v)

                                def on_error(self, e): logger.exception("rx error", exc_info=e)

                                def on_completed(self): pass

                            self._rx_subscription = rx_conn.subscribe(_Observer())
                        except Exception:
                            logger.exception("Failed to subscribe to transport.reactive")
            except Exception:
                logger.exception("Failed to wire transport.reactive to session routing")

            self._plugin_subscription_guard = True

    def __repr__(self):
        return f"{self.__class__.__name__}({self.id=})"

    def __str__(self):
        return str(self.__session_id)
