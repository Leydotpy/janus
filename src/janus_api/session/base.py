import asyncio
import logging
import threading
from inspect import iscoroutinefunction, isawaitable
from threading import RLock
from typing import Any, Callable, Optional, Mapping, Dict, List, Union, NamedTuple

import pyee.asyncio

from janus_api.conf import settings
from janus_api.core.exceptions import PluginNotRegistered
from janus_api.lib.manager import PluginManager
from janus_api.models import JanusRequest
from janus_api.models.request import AttachPluginRequest, DetachPluginRequest
from janus_api.transport.websocket import WebsocketTransportClient
from janus_api.transport.websocket import create_socket_client


logger = logging.getLogger(__name__)


# ---------- Small typed helper namedtuple ----------
class SessionLazyAttribute(NamedTuple):
    factory: Callable[[], Any]
    eager: bool = False
    # validator should be a no-arg callable that raises on invalid config
    validator: Optional[Callable[[], None]] = None


# ---------- Async transport factory (unchanged) ----------
async def create_transport() -> Any:
    url = getattr(settings, "JANUS_SESSION_URL", None)
    if not url:
        raise AttributeError("JANUS_SESSION_URL is not configured.")
    if str(url).startswith("ws://") or url.startswith("wss://"):
        return await create_socket_client(str(url))
    import httpx
    return httpx.AsyncClient(base_url=str(url))


def run_transport_validator():
    url = getattr(settings, "JANUS_SESSION_URL", None)
    if not url:
        raise AttributeError(
            "'JANUS_SESSION_URL' has not been configured. "
            "Please configure 'JANUS_SESSION_URL=<your_session_url>' in the settings module to create a new session."
        )


# ---------- Robust, reusable lazy descriptor ----------
class LazyAttributeAccess:
    """
    Descriptor that supports both synchronous factories and coroutine factories.
    - If factory() returns a plain object -> cache & return it.
    - If factory() returns a coroutine (awaitable):
        - If called inside a running event loop, a Task is scheduled and returned.
          (Callers in async code should `await` the Task to get the real object.)
        - If called outside an event loop, the coroutine is run synchronously (new loop)
          and the concrete result is cached and returned.
    Notes:
    - Eager creation (eager=True) is allowed only for sync factories. Eager with async factories raises ValueError.
    - Validator is optional no-arg callable that will be called before factory is invoked.
    """

    def __init__(self, /, factory: Callable[[], Any], eager: bool = False, *,
                 validator: Optional[Callable[[], None]] = None) -> None:
        # defensive name for messages
        self._factory_repr = getattr(factory, "__name__", repr(factory))
        if not callable(factory):
            raise TypeError(f"factory '{self._factory_repr}' is not callable")

        self._factory = factory
        self.eager = bool(eager)
        self._lock = RLock()
        self._private_name: Optional[str] = None
        self._public_name: Optional[str] = None
        self._validator = validator
        self._needs_validation = bool(validator)
        self._is_coroutine_factory = iscoroutinefunction(factory)

        if self._is_coroutine_factory and self.eager:
            # cannot eager-create coroutine factory at class-creation time safely
            raise ValueError("cannot eager-create an async factory at class creation time (eager=True)")

    def __set_name__(self, owner, name: str):
        # invoked at class creation time
        self._public_name = name
        self._private_name = f"_{name}_cached"

        if self.eager:
            # eager creation for sync factories only (we validated this in __init__)
            with self._lock:
                if not hasattr(owner, self._private_name):
                    val = self._create_value_sync(owner)
                    setattr(owner, self._private_name, val)

    def _run_validator(self):
        if self._needs_validation and self._validator is not None:
            # validator is expected to be a no-arg function that raises if invalid
            self._validator()

    def _create_value_sync(self, owner):
        """
        Create value synchronously (used for eager creation or when no running loop).
        If factory returns coroutine, run it in a new loop and return the result.
        """
        rv = self._factory()
        if isawaitable(rv):
            # run coroutine to completion in a fresh loop (synchronous fallback)
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(rv)
            finally:
                loop.close()
        return rv

    def _create_value_async(self, owner):
        """
        Create value when event loop is running: schedule a Task and return it immediately.
        """
        rv = self._factory()
        if isawaitable(rv):
            loop = asyncio.get_running_loop()
            task = loop.create_task(rv)
            return task
        return rv

    def __get__(self, instance, owner):
        klass = owner if owner is not None else type(instance)
        # return cached
        if hasattr(klass, self._private_name):
            return getattr(klass, self._private_name)

        with self._lock:
            if hasattr(klass, self._private_name):
                return getattr(klass, self._private_name)
            # validate first
            self._run_validator()

            # create concrete value depending on whether an event loop is running
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # no running event loop -> create synchronously
                val = self._create_value_sync(klass)
            else:
                # running loop: schedule coroutine into loop (if any)
                if self._is_coroutine_factory:
                    # factory returns coroutine -> schedule a Task
                    val = self._create_value_async(klass)
                else:
                    # sync factory => run immediately
                    val = self._factory()

            setattr(klass, self._private_name, val)
            return val

    def __set__(self, instance, value):
        # set on the class cache (rare but useful for tests)
        klass = type(instance)
        setattr(klass, self._private_name, value)

    def __delete__(self, instance):
        klass = type(instance)
        if hasattr(klass, self._private_name):
            delattr(klass, self._private_name)


# ---------- Safer metaclass (per-class instance + lock initialization) ----------
class SessionMeta(type):
    """
    Creates one singleton instance *per class* using this metaclass.
    Also installs LazyAttributeAccess descriptors for entries in __attrs__ mapping.
    Expected __attrs__ structure: mapping of name -> SessionLazyAttribute(factory, eager=False, validator=None)
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, name, bases, namespace):
        attrs: Mapping[str, SessionLazyAttribute] = namespace.pop("__attrs__", {}) or {}
        if not isinstance(attrs, Mapping):
            raise TypeError("__attrs__ must be a mapping name -> SessionLazyAttribute")

        for key, spec in attrs.items():
            if not isinstance(spec, SessionLazyAttribute):
                raise ValueError(f"spec for '{key}' must be a SessionLazyAttribute instance")
            # respect explicit override in class namespace
            if key in namespace:
                continue
            # validate factory callable
            factory = spec.factory
            if not callable(factory):
                raise TypeError(f"attribute '{key}' must have a callable factory")
            # install descriptor; validator may be None
            namespace[key] = LazyAttributeAccess(factory=factory, eager=bool(spec.eager),
                                                  validator=spec.validator)
        return super().__new__(cls, name, bases, namespace)


    def __call__(cls, *args, **kwargs):
        # per-class singleton creation (thread-safe)
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__call__(*args, **kwargs)
            return cls._instance


# ---------- AbstractBaseSession with robust _setup awaiting ----------
class AbstractBaseSession(metaclass=SessionMeta):
    __slots__ = ("__session_id", "__events", "__transport", "_plugin_subscription_guard",
                 "_plugins_by_handle", "_plugins_by_name", "_rx_subscription")
    __attrs__ = {
        "__transport__": SessionLazyAttribute(factory=create_transport, validator=run_transport_validator),
        "__plugins__": SessionLazyAttribute(factory=PluginManager, eager=True),
    }

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
        return int(self.__session_id)  # type: ignore

    @id.setter
    def id(self, value):
        self.__session_id = value

    @property
    def plugins(self) -> PluginManager:
        # plugins is installed on the class via the metaclass as a LazyAttributeAccess descriptor
        pm = self.__class__.__plugins__
        # if pm is an awaitable (unlikely because PluginManager is sync), allow user to handle accordingly
        return pm

    @property
    def events(self):
        return self.__events

    @property
    def transport(self) -> WebsocketTransportClient:
        return self.__transport

    async def send(self, data: JanusRequest):
        # ensure a transport is created/awaited before sending
        if self.transport is None:
            await self._setup()
        return await self.transport.send(data)

    async def attach(self, plugin: str):
        if not self.__session_id:
            raise ValueError("Session ID is not set. Cannot attach plugin.")
        message = AttachPluginRequest(janus="attach", plugin=plugin, session_id=self.id)
        response = await self.send(message)
        if response.janus != "success" or not hasattr(response, "data"):
            raise RuntimeError(f"Attach plugin failed with Janus response '{response.janus}'.")
        plugin_id = response.data.id
        return plugin_id

    async def detach(self, handle_id):
        message = DetachPluginRequest(janus="detach", session_id=self.id, handle_id=handle_id)
        response = await self.send(message)
        if response.janus != "success":
            raise RuntimeError(f"Detach plugin failed with Janus response '{response.janus}'.")
        try:
            del self.plugins[handle_id]
        except Exception as exc:
            logger.exception("Failed to detach plugin.", exc_info=exc)
        return handle_id

    async def create(self):
        raise NotImplementedError()

    async def destroy(self, **kwargs):
        self.plugins.clear()
        if self.transport:
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
            # transport.stop may be async — await it if needed
            stop_result = self.transport.stop()
            if isawaitable(stop_result):
                await stop_result

    async def _setup(self):
        """set up the connection to the websocket server
        called in the .create() method.
        """
        # If transport already set and open -> nothing to do
        if self.transport and getattr(self.transport, "open", False):
            logger.info("Transport already open; skipping setup.")
            return

        cls = self.__class__
        transport_attr = cls.__transport__

        # If descriptor returned an awaitable (Task/coroutine), await it to get the real transport
        if isawaitable(transport_attr):
            try:
                transport = await transport_attr
            except Exception:
                # If scheduled task failed, re-raise as runtime error to surface config problems
                logger.exception("Failed to create transport from async factory", exc_info=True)
                raise
        else:
            transport = transport_attr

        if transport is None:
            raise RuntimeError("transport factory not configured")

        # set instance transport
        self.__transport = transport

        # wire reactive events if present
        try:
            rx_conn = getattr(self.transport, "events", None)
            if rx_conn is not None and self._rx_subscription is None:
                def _rx_on_next(payload):
                    try:
                        self._route_event(payload)
                    except Exception as excp:
                        logger.exception("Error routing event from reactive stream", exc_info=excp)

                try:
                    # subscribe may be sync; keep defensive handling
                    self._rx_subscription = rx_conn.subscribe(
                        _rx_on_next,
                        lambda err: logger.error(f"RX event error: {err}", exc_info=err)
                    )
                except Exception as exc:
                    logger.exception("Error wiring subscription", exc_info=exc)
        except Exception as e:
            logger.exception("Failed to wire transport.reactive to session routing", exc_info=e)

    def _route_event(self, evt):
        logger.debug("Routing event %s", evt)
        try:
            if isinstance(evt, dict):
                payload = evt.get("payload", evt)
                sender = evt.get("sender", evt.get("from"))
            else:
                payload = evt
                sender = getattr(evt, "sender", getattr(evt, "from", None))

            pm = self.plugins

            if sender and hasattr(pm, "dispatch"):
                try:
                    pm.dispatch(str(sender), payload)
                    return
                except PluginNotRegistered:
                    logger.debug("No registered plugin found for sender %s", sender)
                except Exception as e:
                    logger.exception("PluginManager.dispatch failed for sender %s", sender, exc_info=e)
        except Exception as exc:
            logger.exception("Error routing plugin event", exc_info=exc)

    def __repr__(self):
        return f"{self.__class__.__name__}({self.id=})"

    def __str__(self):
        return str(self.__session_id)
