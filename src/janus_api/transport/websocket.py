"""
A WebSocket-based transport client for asynchronous communication with the Janus WebRTC Gateway.

This module provides the WebsocketTransportClient class, which allows for professional,
asynchronous WebSocket communication. The class integrates with ReactiveX (RxPY) for
event stream handling, supports JSEP (JavaScript Session Establishment Protocol)
extraction, and provides transaction management for robust operation. Additionally,
it features Pydantic-based validation for incoming and outgoing data.

Exports:
- WebsocketTransportClient: A professional WebSocket client built with asyncio and RxPY.
- Events: Enumerates specific event types emitted by the client.
"""
import asyncio
import enum
import json
import logging
import uuid
from typing import Dict, Optional, Any, Literal

# Third-party imports
import websockets
from pydantic import TypeAdapter, ValidationError
from reactivex import Observable
from reactivex.subject import Subject
from websockets.client import ClientProtocol

# Local imports
from janus_api.conf import settings
from janus_api.models import JanusResponse, JanusRequest
from janus_api.models.response import Jsep

LOG_PATH = getattr(settings, "LOG_PATH")

# Configure Logging
logger = logging.getLogger(__name__)


class Events(enum.StrEnum):
    TRANSPORT = "janus.transport"
    SDP = "janus.sdp"
    WEBRTC = "janus.webrtc"
    ERROR = "janus.error"
    CLOSE = "janus.close"


class WebsocketTransportClient:
    """
    High-level client for managing a WebSocket connection with reactive event handling.

    This class is designed to handle WebSocket communication with reconnect support, transaction
    management, and Reactivex observable event streams. It is primarily used for environments requiring
    real-time message exchange with remote peers and supports dispatching WebSocket-driven events like
    signaling, media updates, and connection state changes.

    Attributes:
        DISPATCHABLE_EVENTS (set[str]): Immutable set of WebSocket events that can be dispatched
        to an observable ReactiveX stream.

    Methods:
        events: Property for accessing the publicly observable Reactivex event stream.
        open: Property indicating the connection state as a boolean value.
        start: Initiates the WebSocket connection loop while waiting for an initial connection.
        stop: Terminates the WebSocket connection and performs cleanup operations.
        connect_reactive: Establishes a connection to the reactive observable stream.
        disconnect_reactive: Disconnects from the reactive observable stream.
        send: Sends a WebSocket message and awaits response in a transactional manner.
    """

    # Events that should be dispatched to the Rx stream
    DISPATCHABLE_EVENTS = {
        'webrtcup', 'hangup', 'media', 'slowlink', 'detached', 'event'
    }

    def __init__(self, url: str = 'ws://localhost:8188/', protocol: str = 'janus-protocol'):
        self._url = url
        self._protocol = protocol
        self._connection: Optional[ClientProtocol] = None

        # Dictionary mapping transaction IDs to pending Futures
        self._transactions: Dict[str, Dict[str, asyncio.Future[Any] | str]] = {}

        # Main task for the receive loop
        self._listen_task: Optional[asyncio.Task] = None

        # Connection state event
        self._connected_event = asyncio.Event()

        # Subject is already hot/multicast, so it can be consumed directly.
        self._event_subject = Subject()
        # Pre-compile the Pydantic validator for performance
        self._response_adapter: TypeAdapter[JanusResponse] = TypeAdapter(JanusResponse)

        self._connect_lock = asyncio.Lock()
        self._stop = False

        self._metrics: Dict[
            Literal[
                "received",
                "futures_resolved",
                "errors",
                "webrtc_events",
                "keepalive",
            ], int] = {
            "received": 0,
            "futures_resolved": 0,
            "errors": 0,
            "webrtc_events": 0,
            "keepalive": 0,
        }

    @property
    def events(self) -> Observable:
        """Public accessor for the ReactiveX event stream."""
        return self._event_subject

    @property
    def open(self):
        return self._connection is not None and self._connected_event.is_set()

    async def start(self):
        """
        Asynchronously starts the connection if it is not already open.

        This method acquires a connection lock to ensure thread safety while starting
        the connection process. If a connection is already established and open,
        the method will return without performing any actions. Otherwise, it resets the
        stop state to False and initiates the connection.

        Raises:
            Any exceptions that may occur during the connection process.
        """
        async with self._connect_lock:
            if self._connection and self.open:
                return
            self._stop = False
            await self._connect()

    async def stop(self):
        """
        Stops the current operation and disconnects.

        Summary:
        This asynchronous method initiates the stopping process by setting
        the stop condition to False and then invokes the disconnection
        mechanism to terminate any active connections.

        Raises:
            No errors explicitly raised from this method.
        """
        self._stop = True
        await self._disconnect()

    async def connect_reactive(self):
        """
        Compatibility no-op.

        The transport emits on a hot Subject, so subscribers receive events without
        requiring an explicit ReactiveX connection step.
        """
        return self._event_subject

    async def disconnect_reactive(self):
        """
        Compatibility no-op.

        The event subject is lifecycle-bound to the transport instance rather than an
        explicit Rx connection handle.
        """
        return None

    async def _connect(self) -> 'WebsocketTransportClient':
        """
        Starts the persistent reconnection loop and waits for the first successful connection.
        """
        if self._listen_task and not self._listen_task.done():
            return self  # Already running

        logger.info(f"Starting connection loop for {self._url}...")
        self._listen_task = asyncio.create_task(self._connection_loop())

        try:
            # Wait for the first successful connection before returning
            await asyncio.wait_for(self._connected_event.wait(), timeout=10.0)
            return self
        except asyncio.TimeoutError:
            # If we can't connect initially, stop the loop and raise
            await self.stop()
            raise ConnectionError(f"Could not establish initial connection to {self._url}")

    async def _disconnect(self):
        """Gracefully closes the connection and cleanup running tasks."""
        logger.info("Disconnecting...")
        self._connected_event.clear()

        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None

        if self._connection:
            await self._connection.close()
            self._connection = None

        self._fail_pending_transactions(ConnectionError("Client disconnected"))

    def _emit(self, payload: dict):
        try:
            self._event_subject.on_next(payload)
        except Exception as e:
            logger.exception("Error emitting payload: %s", e)

    async def __aenter__(self):
        """Async Context Manager Entry"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async Context Manager Exit"""
        await self.stop()

    @staticmethod
    def _generate_transaction_id() -> str:
        """Generates a random 12-character alphanumeric string."""
        return uuid.uuid4().hex

    async def send(self, message: JanusRequest, timeout: Optional[float] = None) -> JanusResponse:
        """
        Sends a JanusRequest over the WebSocket connection and waits for a response.

        This method sends a JanusRequest message to the connected WebSocket and waits for
        a response that matches the specified transaction ID in the message. It ensures thread-safety
        by checking connection status through an event flag, tracks ongoing transactions using a
        transaction ID, and provides timeout handling for operations.

        Parameters:
            message (JanusRequest): The request object to be sent. Must be compatible with the expected Janus server API.

            timeout (Optional[float]): The maximum time, in seconds, to wait for a response before raising a TimeoutError. Defaults to None, which waits indefinitely.

        Returns:
            JanusResponse: The response object received from the WebSocket server, corresponding
            to the given request.

        Raises:
            ConnectionError: If the WebSocket is not currently connected.
            asyncio.TimeoutError: If the response is not received within the specified timeout.
            Exception: If there are errors during message sending or processing.
        """
        # Check event instead of connection object for thread-safety
        if not self._connected_event.is_set():
            raise ConnectionError("WebSocket is not currently connected.")

        tx_id = self._generate_transaction_id()
        message.transaction = tx_id

        # Create a Future to track this specific request
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        tx_in = {'future': future, 'request': message.janus}
        self._transactions[tx_id] = tx_in

        try:
            logger.info("sending %s request", str(message.janus))
            await self._connection.send(message.model_dump_json())
            # Wait for the listener to find the matching response
            result = await asyncio.wait_for(future, timeout=timeout) if timeout else await future
            logger.info("Received response %s::<<<metrics>>>%s" % (result.json(), self._metrics))
            return result
        except asyncio.TimeoutError as e:
            logger.error(f"Transaction {tx_id} timed out.", exc_info=e)
            del self._transactions[tx_id]
            raise
        except Exception as e:
            logger.error("Error sending message: %s", e, exc_info=e)
            if tx_id in self._transactions:
                del self._transactions[tx_id]
            raise

    async def _connection_loop(self):
        """
        Persistent loop that maintains the WebSocket connection.
        Uses websockets.connect as an async iterator to handle automatic reconnection and backoff.
        """
        try:
            async for websocket in websockets.connect(
                    self._url,
                    subprotocols=[self._protocol],  # type: ignore
                    ping_interval=20,
                    ping_timeout=20
            ):
                try:
                    logger.info("WebSocket connection established.")
                    self._connection = websocket
                    self._connected_event.set()

                    try:
                        await self._process_message()
                    except Exception as e:
                        logger.exception(f"failed to process with exception: {e}")

                except websockets.ConnectionClosed as e:
                    logger.warning(f"Connection lost: {e.rcvd.code} - {e.rcvd.reason}. Reconnecting...")
                except Exception as e:
                    logger.error("Unexpected error in connection loop: %s", str(e), exc_info=e)
                finally:
                    # Cleanup state for this specific connection attempt
                    self._connected_event.clear()
                    self._connection = None
                    self._fail_pending_transactions(ConnectionError("Connection lost"))

        except asyncio.CancelledError:
            logger.info("Connection loop cancelled.")
        except Exception as e:
            logger.critical("Fatal error in connection loop: %s", str(e), exc_info=e)

    def _fail_pending_transactions(self, exception: Exception):
        """Cancels all pending transactions with the given exception."""
        for tx_id, tx_in in list(self._transactions.items()):
            future = tx_in.get("future")
            if future is not None and not future.done():
                future.set_exception(exception)
        self._transactions.clear()

    async def _process_message(self):
        """
        Core logic for routing messages.
        Refactored to follow receiveMessage pattern:
        1. Loop & Parse
        2. Extract JSEP
        3. Validate Pydantic
        4. Handle ACK -> Handle Transaction -> Handle Async Event
        """
        async for raw_message in self._connection:  # type: ignore
            # --- 1. PARSE & METRICS ---
            try:
                data = json.loads(raw_message)
                self._metrics["received"] += 1
            except json.JSONDecodeError:
                logger.error("Received malformed JSON.")
                continue
            except Exception as e:
                logger.exception("Error processing message: %s", str(e), exc_info=e)
                continue

            # --- 2. EXTRACT & DISPATCH JSEP (Pre-Validation) ---
            # We pop 'jsep' so it doesn't interfere with Pydantic validation of the main body
            jsep_data = data.get('jsep')
            tx_id = data.get('transaction')

            # --- 3. PYDANTIC VALIDATION ---
            try:
                response_model = self._response_adapter.validate_python(data, strict=False)
                janus_type = getattr(response_model, 'janus', None)
            except ValidationError as e:
                logger.error("Validation Error: %s", str(e), exc_info=e)
                continue

            sender = getattr(response_model, "sender", data.get("sender"))

            if jsep_data:
                try:
                    jsep_obj = getattr(response_model, "jsep", None) or Jsep(**jsep_data)
                    self._emit({
                        'event': Events.SDP,
                        'payload': jsep_obj,
                        'from': sender,
                        'sender': sender,
                    })
                    self._metrics["webrtc_events"] += 1
                except ValidationError as e:
                    logger.error("Received invalid JSEP structure.", exc_info=e)

            # --- 4. HANDLE ACK ---
            if tx_id and janus_type == 'ack':
                logger.debug(f"ACK received for {tx_id}")

                if tx_id in self._transactions:
                    tx_in = self._transactions[tx_id]
                    # Only resolve Keepalives on ACK, others wait for 'success'
                    if tx_in['request'] == 'keepalive':
                        tx_in['future'].set_result(response_model)
                        del self._transactions[tx_id]
                        self._metrics["keepalive"] += 1
                        logger.info(f"Closed Keepalive {tx_id}")
                continue

            # --- 5. HANDLE TRANSACTION RESPONSE (Success/Error/Event) ---
            # If this ID exists in our pending transactions, resolve it.
            if tx_id and tx_id in self._transactions:
                tx_in = self._transactions[tx_id]
                future = tx_in['future']

                if not future.done():
                    if janus_type == 'error':
                        # Extract error reason for cleaner exceptions
                        reason = getattr(response_model.error, 'reason', 'Unknown Error')
                        future.set_exception(Exception(f"Janus Error: {reason}"))
                        self._metrics["errors"] += 1
                    else:
                        future.set_result(response_model)
                        self._metrics["futures_resolved"] += 1

                # Clean up and exit loop step (mirrors receiveMessage logic)
                del self._transactions[tx_id]
                logger.debug(f"Closed transaction {tx_id} with {janus_type}")
                continue

            # --- 6. HANDLE ASYNC EVENTS (Fallback) ---
            # If it wasn't an ACK and wasn't a Transaction, it's a push event
            if str(janus_type) in self.DISPATCHABLE_EVENTS:
                logger.info(f"Dispatching Async Event: {janus_type}")
                self._emit({
                    'event': Events.WEBRTC,
                    'payload': response_model,
                    'from': sender,
                    'sender': sender,
                })
                self._metrics["webrtc_events"] += 1


async def create_socket_client(url: str) -> WebsocketTransportClient:
    client = WebsocketTransportClient(url)
    await client.start()
    return client
