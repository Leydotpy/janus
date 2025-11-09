"""WebsocketTransportClient with optional reactivex integration.

This file also contains helper create_transport used by the SessionMeta below.
"""
import asyncio
import enum
import json
import logging
import random
import uuid
from typing import (Any, AnyStr, Optional, Dict, Callable, )

import pyee
import websockets
from pydantic import TypeAdapter, ValidationError
from reactivex import (Observable, Subject as RxSubject, operators as rx_ops, )
from websockets import WebSocketException, ConnectionClosedError, ConnectionClosedOK

from janus_api.models import JanusRequest, JanusResponse
from janus_api.models.response import AckResponse, EventResponse, ErrorResponse, SuccessResponse, KeepAliveResponse, \
    WebRTCEvent, Jsep

logger = logging.getLogger("janus.transport")


def show_error(exception, **kwargs):
    line = kwargs.get("line", '____')
    user_message = kwargs.get("message", "Unknown error")
    logger.exception(f"Exception raised by Janus transport in {__file__}: line {line}. {user_message}: %s",
                     str(exception))


# -------------------------
# WebsocketTransportClient
# -------------------------
class WebsocketTransportClient:
    """Robust websocket transport for Janus with optional reactivex Subject.

    - start()/stop() lifecycle
    - transaction -> Future mapping
    - pyee AsyncIOEventEmitter for compatibility
    - optional rx connectable observable emitting EventResponse objects
    """

    MAX_RETRIES = 5
    INITIAL_DELAY = 1.0
    MAX_DELAY = 60.0
    CIRCUIT_BREAKER_TIMEOUT = 300.0

    class Events(enum.StrEnum):
        TRANSPORT = "janus.transport"
        SDP = "janus.sdp"
        WEBRTC = "janus.webrtc"
        ERROR = "janus.error"
        CLOSE = "janus.close"

    def __init__(self, url: AnyStr, *, enable_reactive: bool = False):
        self.url: str = url
        self._ws: Optional[Any] = None
        self._txn: Dict[str, asyncio.Future] = {}
        # pyee emitter (guarded)
        self._emitter: Optional[Any] = pyee.asyncio.AsyncIOEventEmitter() if pyee is not None else None

        # reactive pieces: base subject (producer), connectable (exposed), connection disposable
        self._rx_base: Optional[RxSubject] = None
        self._rx_connectable = None
        self._rx_connection = None

        if enable_reactive:
            base = RxSubject()
            connectable = base.pipe(rx_ops.publish())
            self._rx_base = base
            self._rx_connectable = connectable
            # expose the connectable as the "reactive" observable
            self._rx_subject = self._rx_connectable
        else:
            self._rx_subject = None

        self._receiver_task: Optional[asyncio.Task] = None
        self._connect_lock = asyncio.Lock()
        self._stop = False
        self._retry_counter = 0
        self._circuit_open = False
        # optional handlers map (string->callable)
        self._handlers: Dict[str, Callable] = {}

    # -----------------
    # lifecycle
    # -----------------
    async def start(self) -> None:
        async with self._connect_lock:
            if self._ws and self.open:
                return
            self._stop = False
            await self._connect()

    async def stop(self) -> None:
        self._stop = True
        if self._receiver_task:
            self._receiver_task.cancel()
            try:
                await self._receiver_task
            except asyncio.CancelledError:
                print("receiver task successfully cancelled")
                logger.info("receiver successfully cancelled")
                pass
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                print(str(e))
                logger.exception(f"websocket close exception raised in {__file__}:line 129 with exception %s", str(e))
                pass
            self._ws = None
        for txn, fut in list(self._txn.items()):
            if not fut.done():
                try:
                    fut.set_exception(ConnectionError("Websocket Transport to Janus server is closed"))
                except Exception as e:
                    print(str(e))
                    logger.exception(f"Exception raised in {__file__}:line 138 with exception %s", str(e))
                    pass
            try:
                del self._txn[txn]
            except Exception as e:
                print(str(e))
                logger.exception(f"Exception raised in {__file__}:line 144 with exception %s", str(e))
                pass

        # disconnect reactive connection & complete base subject
        try:
            if self._rx_connection is not None:
                if hasattr(self._rx_connection, "dispose"):
                    self._rx_connection.dispose()
                elif hasattr(self._rx_connection, "close"):
                    self._rx_connection.close()
                else:
                    try:
                        self._rx_connection()
                    except Exception as e:
                        print(str(e))
                        logger.exception(f"rxpy exception raised in {__file__}:line 159 with exception %s", str(e))
                        pass
        except Exception as e:
            print(str(e))
            logger.exception(
                f"Exception raised in {__file__}:line 162. Failed while disconnecting reactive connection: %s", str(e))
        finally:
            self._rx_connection = None

        try:
            if self._rx_base is not None:
                self._rx_base.on_completed()
        except Exception as e:
            print(str(e))
            logger.exception(f"Exception raised in {__file__}:line 172. failed to complete base rx subject: %s", str(e))
        finally:
            self._rx_base = None
            self._rx_connectable = None
            self._rx_subject = None

        try:
            if self._emitter is not None:
                self._emitter.remove_all_listeners()
        except Exception as e:
            print(str(e))
            logger.exception(f"Exception raised in {__file__}:line 183 with exception %s", str(e))
            pass
        self._retry_counter = 0
        self._circuit_open = False

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()

    # -----------------
    # reactive helpers
    # -----------------
    async def connect_reactive(self):
        """Connect the internal connectable observable; idempotent."""
        if self._rx_connectable is None:
            return None
        if self._rx_connection is not None:
            return self._rx_connection
        try:
            # connectable.connect() returns a Disposable
            self._rx_connection = self._rx_connectable.connect()
            return self._rx_connection
        except Exception as e:
            print(str(e))
            logger.exception(f"Exception raised in {__file__}:line 210. Failed to connect reactive connectable: %s",
                             str(e))
            return None

    async def disconnect_reactive(self):
        """Disconnect the internal connectable observable (if connected)."""
        if self._rx_connection is None:
            return
        try:
            if hasattr(self._rx_connection, "dispose"):
                self._rx_connection.dispose()
            elif hasattr(self._rx_connection, "close"):
                self._rx_connection.close()
            else:
                try:
                    self._rx_connection()
                except Exception as e:
                    print(str(e))
                    logger.exception(f"Exception raised in {__file__}:line 227 with exception %s", str(e))
                    pass
        except Exception as e:
            print(str(e))
            logger.exception(f"Exception raised in {__file__}:line 231. Failed to disconnect reactive connection: %s",
                             str(e))
        finally:
            self._rx_connection = None

    @property
    def reactive(self) -> Optional[Observable]:
        """Expose the connectable observable (or None)."""
        return self._rx_subject

    # -----------------
    # internal connection & receive
    # -----------------
    async def _connect(self) -> None:
        if self._circuit_open:
            logger.warning("Circuit is open, not connecting right now")
            return

        try:
            if websockets is None:
                raise RuntimeError("websockets library not installed")
            self._ws = await websockets.connect(self.url, subprotocols=["janus-protocol"], ping_interval=10,
                                                ping_timeout=10, compression=None, )
            self._retry_counter = 0
            self._receiver_task = asyncio.create_task(self._receive_loop(), name="janus-recv")
            if self._emitter is not None:
                try:
                    self._emitter.emit("open")
                except Exception:
                    pass
            await self._push_to_rx_subject({"type": "janus.transport", "event": "websocket.open"})
            logger.info("Connected to %s", self.url)
        except (WebSocketException, ConnectionRefusedError) as e:
            logger.warning("Connect failed: %s", e)
            await self._schedule_retry()

    async def _schedule_retry(self) -> None:
        if self._retry_counter >= self.MAX_RETRIES:
            self._circuit_open = True
            asyncio.create_task(self._reset_circuit())
            return
        delay = min(self.INITIAL_DELAY * (2 ** self._retry_counter) + random.uniform(0, 1), self.MAX_DELAY)
        self._retry_counter += 1
        await asyncio.sleep(delay)
        if not self._stop:
            await self._connect()

    async def _reset_circuit(self) -> None:
        await asyncio.sleep(self.CIRCUIT_BREAKER_TIMEOUT)
        self._circuit_open = False
        self._retry_counter = 0
        if not self._stop:
            await self._connect()

    # helper to push into base subject
    async def _push_to_rx_subject(self, payload: dict):
        base = getattr(self, "_rx_base", None)
        if base is None:
            return
        try:
            base.on_next(payload)
        except Exception as e:
            logger.exception("rx subject on_next failed (async push)", exc_info=e)

    async def _receive_loop(self) -> None:
        """
        Strict receive loop for Janus websocket.

        Behavior notes:
        - This version prefers strict validation with Pydantic if available (TypeAdapter).
        - It also pushes a normalized payload into the base reactive subject (if available).
        """
        ws = getattr(self, "_ws", None)
        if ws is None:
            return

        # Adapter cache for reuse
        _ADAPTER_CACHE: dict[type, TypeAdapter[Any]] = {}

        def _get_adapter[T](model_cls: type[T]) -> TypeAdapter[T]:
            if TypeAdapter is None:
                raise RuntimeError("pydantic TypeAdapter is not available")
            adapter_ = _ADAPTER_CACHE.get(model_cls)
            if adapter_ is None:
                adapter_ = TypeAdapter(model_cls)  # type: TypeAdapter[T]
                _ADAPTER_CACHE[model_cls] = adapter_
            return adapter_

        def _is_typed(obj: object) -> bool:
            return hasattr(obj, "model_dump") or (hasattr(obj, "dict") and hasattr(obj, "__class__"))

        def _extract(obj: object, field: str, default=None):
            if _is_typed(obj):
                return getattr(obj, field, default)
            if isinstance(obj, dict):
                return obj.get(field, default)
            return default

        def _emit_jsep(event_obj: object) -> None:
            """Emit jsep payload strictly (expects validated EventResponse instance)."""
            if not _is_typed(event_obj):
                raise TypeError("event_obj must be a validated EventResponse (pydantic model instance)")
            jsep_raw = getattr(event_obj, "jsep", None)
            if jsep_raw is None:
                return
            # strict validate Jsep
            if TypeAdapter is None:
                jsep_typed = jsep_raw
            else:
                jsep_typed = _get_adapter(Jsep).validate_python(jsep_raw)
            sender = getattr(event_obj, "sender", None)
            plugindata = getattr(event_obj, "plugindata", None)
            plugin_name = getattr(plugindata, "plugin", None) if plugindata is not None else None
            if self._emitter is not None:
                try:
                    if plugin_name:
                        self._emitter.emit("event", {"type": self.Events.SDP, "from": sender, "plugin": plugin_name,
                                                     "payload": jsep_typed, })
                    else:
                        self._emitter.emit("event", {"type": self.Events.SDP, "from": sender, "payload": jsep_typed})
                except Exception as exc:
                    show_error(str(exc), line="353", user_message="Failed to emit jsep payload")
            if getattr(self, "_rx_base", None) is not None:
                # schedule non-blocking push to rx base with typed jsep model
                try:
                    asyncio.create_task(self._push_to_rx_subject(
                        {"type": self.Events.SDP, "from": sender, "plugin": plugin_name, "event": jsep_typed}))
                except Exception as exc:
                    show_error(str(exc), line="362", user_message="failed to schedule push of jsep to rx base")

        def _sanitize_build[T](adapter_cls: TypeAdapter[T], typed_source: type[T], raw_data,
                               remove_fields: set[str] = None) -> T:
            remove_fields = remove_fields or set()
            if typed_source is not None and _is_typed(typed_source):
                dump = typed_source.model_dump()
                for f in remove_fields:
                    dump.pop(f, None)
                return adapter_cls.validate_python(dump)
            if remove_fields:
                raw_copy = dict(raw_data)
                for f in remove_fields:
                    raw_copy.pop(f, None)
                return adapter_cls.validate_python(raw_copy)
            return adapter_cls.validate_python(raw_data)

        MODEL_MAP: dict[str, type[Any]] = {"event": EventResponse, "success": SuccessResponse,
                                           "keepalive": KeepAliveResponse, "error": ErrorResponse, }

        async def _maybe_run_handler(handler_fn, model_instance):
            try:
                res = handler_fn(model_instance)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                logger.exception("user handler_fn raised an exception", exc_info=True)

        _metrics = {"received": 0, "parsed_typed": 0, "futures_resolved": 0, "webrtc": 0}

        try:
            async for raw in ws:
                _metrics["received"] += 1

                if isinstance(raw, (bytes, bytearray)):
                    try:
                        raw = raw.decode("utf-8")
                    except Exception:
                        raw = raw.decode("utf-8", errors="replace")

                try:
                    data = json.loads(raw)
                except Exception:
                    logger.exception("Failed to parse JSON message: %r", raw)
                    continue

                try:
                    if TypeAdapter is None:
                        parsed = data
                        parsed_typed = False
                    else:
                        parsed = _get_adapter(JanusResponse).validate_python(data)
                        parsed_typed = True
                        _metrics["parsed_typed"] += 1
                except ValidationError:
                    # strict mode: re-raise so callers can detect mismatch
                    raise

                janus_type = _extract(parsed, "janus")
                txn = _extract(parsed, "transaction")
                # ACK handling
                if txn and janus_type == "ack":
                    fut = self._txn.pop(txn, None)
                    if fut is None:
                        logger.warning("ack for unknown txn=%s", txn)
                        continue
                    if fut.done():
                        logger.warning("future for txn=%s already done when processing ack", txn)
                        continue
                    if TypeAdapter is None:
                        result = data
                    else:
                        ack_adapter = _get_adapter(AckResponse)
                        result = _sanitize_build(ack_adapter, parsed if parsed_typed else None, data)
                    try:
                        fut.set_result(result)
                    except Exception:
                        pass
                    _metrics["futures_resolved"] += 1
                    continue
                fut = None
                if txn:
                    fut = self._txn.pop(txn, None)
                # Transactional message handling
                if fut:
                    if janus_type == "event":
                        adapter = _get_adapter(EventResponse) if TypeAdapter is not None else None
                        event_typed = _sanitize_build(adapter, parsed if parsed_typed else None,
                                                      data) if adapter is not None else data
                        # emit jsep separately (event_typed validated)
                        try:
                            _emit_jsep(event_typed)
                        except Exception:
                            # allow _emit_jsep to propagate ValidationErrors
                            raise
                        result_typed = _sanitize_build(adapter, event_typed, data,
                                                       remove_fields={"jsep"}) if adapter is not None else data
                        if not fut.done():
                            fut.set_result(result_typed)
                            _metrics["futures_resolved"] += 1
                        handler = getattr(self, "_handlers", {}).get("event")
                        if handler:
                            asyncio.create_task(_maybe_run_handler(handler, event_typed))
                    elif janus_type in ("success", "keepalive", "error"):
                        # TODO: propagate error message instead of resolving it
                        model_cls = MODEL_MAP.get(janus_type)
                        adapter = _get_adapter(model_cls) if TypeAdapter is not None else None
                        result_typed = _sanitize_build(adapter, parsed if parsed_typed else None,
                                                       data) if adapter is not None else data
                        if not fut.done():
                            fut.set_result(result_typed)
                            _metrics["futures_resolved"] += 1
                        handler = getattr(self, "_handlers", {}).get(janus_type)
                        if handler:
                            asyncio.create_task(_maybe_run_handler(handler, result_typed))
                    else:
                        adapter = _get_adapter(WebRTCEvent) if TypeAdapter is not None else None
                        ev = _sanitize_build(adapter, parsed if parsed_typed else None,
                                             data) if adapter is not None else data

                        sender = getattr(ev, "sender", None)
                        session_id = getattr(ev, "session_id", None)
                        try:
                            if self._emitter is not None:
                                self._emitter.emit("event",
                                                   {"type": self.Events.WEBRTC, "from": sender, "session": session_id,
                                                    "payload": ev, })
                        except Exception:
                            logger.exception("failed to emitter event")
                        if getattr(self, "_rx_base", None) is not None:
                            asyncio.create_task(self._push_to_rx_subject(
                                {"type": self.Events.WEBRTC, "from": sender, "session": session_id, "event": ev}))
                        # if not fut.done():
                        #     fut.set_result(ev)
                        _metrics["webrtc"] += 1
                else:
                    adapter = _get_adapter(WebRTCEvent) if TypeAdapter is not None else None
                    ev = _sanitize_build(adapter, parsed if parsed_typed else None,
                                         data) if adapter is not None else data
                    sender = getattr(ev, "sender", None)
                    session_id = getattr(ev, "session_id", None)
                    if self._emitter is not None:
                        try:
                            self._emitter.emit("event",
                                               {"type": self.Events.WEBRTC, "from": sender, "session": session_id,
                                                "payload": ev, })
                        except Exception:
                            logger.exception("failed to emit webrtc event")
                    if getattr(self, "_rx_base", None) is not None:
                        asyncio.create_task(self._push_to_rx_subject(
                            {"type": self.Events.WEBRTC, "from": sender, "session": session_id, "event": ev}))
                    _metrics["webrtc"] += 1
                    handler = getattr(self, "_handlers", {}).get(janus_type)
                    if handler:
                        asyncio.create_task(_maybe_run_handler(handler, ev))
        except asyncio.CancelledError:
            raise
        except (ConnectionClosedOK, ConnectionClosedError) as e:
            logger.info("Websocket connection closed: %s", e)
        except ValidationError:
            # bubble up for debugging
            raise
        except Exception as e:
            logger.exception("Unexpected error in receive loop", exc_info=True)
            try:
                if self._emitter is not None:
                    self._emitter.emit("event", {"type": self.Events.ERROR, "payload": e, })
                if getattr(self, "_rx_base", None) is not None:
                    asyncio.create_task(self._push_to_rx_subject({"type": self.Events.ERROR, "event": e}))
            except Exception:
                logger.exception("failed to emit error event", exc_info=True)
        finally:
            try:
                if self._emitter is not None:
                    self._emitter.emit("event", {"type": self.Events.CLOSE})
                if getattr(self, "_rx_base", None) is not None:
                    asyncio.create_task(self._push_to_rx_subject({"type": self.Events.CLOSE}))
            except Exception:
                logger.exception("failed to emit close event", exc_info=True)
            try:
                logger.debug("receive loop metrics: %s", _metrics)
            except Exception:
                pass

            if not getattr(self, "_stop", False):
                try:
                    await self._schedule_retry()
                except Exception:
                    logger.exception("failed while scheduling retry", exc_info=True)

    # -----------------
    # send
    # -----------------
    async def send(self, message: JanusRequest, *, timeout: Optional[float] = None) -> JanusResponse:
        if self._circuit_open:
            raise ConnectionError("Circuit is open; refusing to send")

        if not self._ws or not self.open:
            await self.start()
            if not self._ws or not self.open:
                raise ConnectionError("Unable to establish connection")

        txn = getattr(message, "transaction", None) or uuid.uuid4().hex
        try:
            message.transaction = txn
        except Exception:
            pass

        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._txn[txn] = fut

        payload = None
        try:
            if hasattr(message, "model_dump_json"):
                payload = message.model_dump_json()
            else:
                payload = json.dumps(message)
        except Exception:
            payload = json.dumps(message)

        try:
            await self._ws.send(payload)
        except (ConnectionClosedError, ConnectionClosedOK) as e:
            self._txn.pop(txn, None)
            await self._schedule_retry()
            raise e

        try:
            result = await asyncio.wait_for(fut, timeout=timeout) if timeout else await fut
            return result
        except asyncio.TimeoutError:
            self._txn.pop(txn, None)
            raise
        except Exception:
            self._txn.pop(txn, None)
            raise

    # -----------------
    # helpers / properties
    # -----------------
    @property
    def event(self) -> Optional[Any]:
        return self._emitter

    @property
    def open(self) -> bool:
        # websockets client protocol has boolean .open attribute (safer than checking state enum)
        return bool(self._ws and getattr(self._ws, "open", False))

    @property
    def connecting(self) -> bool:
        return bool(
            self._ws and getattr(self._ws, "open", False) is False and getattr(self._ws, "closed", False) is False)

    @property
    def closed(self) -> bool:
        return bool(not self._ws or getattr(self._ws, "closed", False))


# convenience factory used by session code
async def create_socket_client(url: str, *, enable_reactive: bool = True) -> WebsocketTransportClient:
    client = WebsocketTransportClient(url, enable_reactive=enable_reactive)
    await client.start()
    return client
