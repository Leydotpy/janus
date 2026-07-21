"""
JanusAdminMonitor: async WebSocket client to interact with Janus Admin/Monitor API.

Features:
- Connects using WebSockets with `janus-admin-protocol`
- Manages transactions and response dispatching (Futures)
- Convenient async methods for common admin requests (info, list_sessions, list_handles, handle_info, get_status, ping, ...)
- Lightweight in-memory metrics store + configurable polling to build timeseries ready for charts
- Broadcasts new metric datapoints to subscribers via asyncio.Queue
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, List
from typing import Optional, Set, Dict, Any, Tuple

import websockets

from janus_api.contrib.admin._storage import TimescaleStorage
from janus_api.conf import settings

JANUS_ADMIN_SECRET = getattr(settings, "JANUS_ADMIN_SECRET")
JANUS_ADMIN_WS_URL = getattr(settings, "JANUS_ADMIN_WS_URL")

logger = logging.getLogger(__name__)


def _transaction_id() -> str:
    return uuid.uuid4().hex


@dataclass
class MetricsPoint:
    ts: float  # epoch seconds (float)
    values: Dict[str, Any]  # keyed metrics, e.g., {"bytes_in": 12345, "packets_lost": 3}


class JanusBaseAdminMonitor:
    """
    Async WebSocket-based monitor for Janus Admin API.

    Usage:
        monitor = JanusAdminMonitor(ws_url="ws://janus.example:7088/admin", admin_secret="mysecret")
        await monitor.connect()
        info = await monitor.info()
        await monitor.start_polling(interval=2.0)  # optional
    """

    def __init__(
            self,
            ws_url: Optional[str] = None,
            *,
            poll_interval: float = 2.0,
            metrics_retention: int = 300,
            loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self.ws_url = ws_url or JANUS_ADMIN_WS_URL
        self.admin_secret = JANUS_ADMIN_SECRET
        self.poll_interval = poll_interval
        self.metrics_retention = metrics_retention  # number of points to keep per handle
        self.loop = loop or asyncio.get_event_loop()

        self._ws: Optional[websockets.WebSocketClientProtocol] = None # type: ignore
        self._listener_task: Optional[asyncio.Task] = None
        self._response_futures: Dict[str, asyncio.Future] = {}
        self._running = False

        # metrics store: (session_id, handle_id) -> deque[MetricsPoint]
        self.metrics: Dict[Tuple[int, int], Deque[MetricsPoint]] = defaultdict(
            lambda: deque(maxlen=self.metrics_retention)
        )

        # broadcast queue for subscribers (WebSocket endpoint will watch this)
        self._broadcast_queues: Set[asyncio.Queue] = set()

        # background poller
        self._poller_task: Optional[asyncio.Task] = None

    @property
    def state(self) -> int:
        return getattr(self._ws, "state")

    @property
    def connecting(self):
        return bool(self.state == 0)

    @property
    def open(self):
        return bool(self.state == 1)

    @property
    def closing(self):
        return bool(self.state == 2)

    @property
    def closed(self):
        return bool(self.state == 3)

    async def connect(self, timeout: float = 5.0) -> None:
        """
        Open the WebSocket connection using 'janus-admin-protocol' subprotocol.
        """
        if self._ws and not self.closed:
            return

        logger.info("Connecting to Janus admin at %s", self.ws_url)
        self._ws = await asyncio.wait_for(
            websockets.connect(self.ws_url, subprotocols=["janus-admin-protocol"]), timeout=timeout # type: ignore
        )
        self._running = True
        self._listener_task = self.loop.create_task(self._listener())
        logger.info("Connected and listener started")

    async def close(self) -> None:
        self._running = False
        if self._poller_task:
            self._poller_task.cancel()
        if self._listener_task:
            self._listener_task.cancel()
        if self._ws:
            await self._ws.close()
            self._ws = None
        # cancel any pending futures
        for tx, fut in list(self._response_futures.items()):
            if not fut.done():
                fut.cancel()
        self._response_futures.clear()
        logger.info("Closed connection")

    async def _listener(self) -> None:
        """
        Read loop: dispatch responses to awaiting futures based on 'transaction'.
        """
        assert self._ws is not None
        try:
            async for msg in self._ws:
                if isinstance(msg, bytes):
                    data = msg.decode()
                else:
                    data = msg
                try:
                    payload = json.loads(data)
                except Exception as e:
                    logger.exception("Invalid JSON from Janus admin: %s", data, exc_info=e)
                    continue

                tx = payload.get("transaction")
                if tx and tx in self._response_futures:
                    fut = self._response_futures.pop(tx)
                    if not fut.done():
                        fut.set_result(payload)
                else:
                    # Unmatched administrative message: broadcast to subscribers
                    await self._broadcast(payload)
        except asyncio.CancelledError:
            logger.debug("Listener cancelled")
        except websockets.ConnectionClosed:
            logger.info("WebSocket closed by server")
        except Exception as e:
            logger.exception("Listener error: %s", e)
        finally:
            self._running = False

    async def _broadcast(self, payload: Dict[str, Any]) -> None:
        """
        Put payload into all subscriber queues (non-blocking).
        """
        for q in list(self._broadcast_queues):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("A subscriber queue is full; skipping")

    async def send_request(
            self,
            janus_cmd: str,
            *,
            session_id: Optional[int] = None,
            handle_id: Optional[int] = None,
            body: Optional[Dict[str, Any]] = None,
            timeout: float = 5.0,
    ) -> Dict[str, Any]:
        """
        Send a generic admin request and await the response matching the transaction id.
        """
        if not self._ws or self.closed:
            await self.connect()

        tx = _transaction_id()
        req: Dict[str, Any] = {
            "janus": janus_cmd,
            "transaction": tx,
        }
        if self.admin_secret:
            req["admin_secret"] = self.admin_secret
        if session_id is not None:
            req["session_id"] = session_id
        if handle_id is not None:
            req["handle_id"] = handle_id
        if body:
            req.update(body)

        fut = self.loop.create_future()
        self._response_futures[tx] = fut

        payload_text = json.dumps(req)
        logger.debug("Sending admin request: %s", payload_text)
        await self._ws.send(payload_text)

        try:
            response = await asyncio.wait_for(fut, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            # cleanup
            if tx in self._response_futures:
                self._response_futures.pop(tx, None)
            raise

    # Convenience wrapper methods -------------------------------------------------

    async def info(self) -> Dict[str, Any]:
        """Get generic Janus instance info (no secret required per docs)."""
        return await self.send_request("info")

    async def ping(self) -> Dict[str, Any]:
        """Ping/pong for health checks."""
        return await self.send_request("ping")

    async def get_status(self) -> Dict[str, Any]:
        return await self.send_request("get_status")

    async def list_sessions(self) -> List[int]:
        resp = await self.send_request("list_sessions")
        return resp.get("sessions", [])

    async def list_handles(self, session_id: int) -> List[int]:
        resp = await self.send_request("list_handles", session_id=session_id)
        return resp.get("handles", [])

    async def handle_info(self, session_id: int, handle_id: int, plugin_only: bool = False) -> Dict[str, Any]:
        body = {}
        if plugin_only:
            body["plugin_only"] = True
        resp = await self.send_request("handle_info", session_id=session_id, handle_id=handle_id, body=body)
        return resp.get("info", resp)

    # Polling + analytics helpers -----------------------------------------------

    async def _poll_once(self) -> None:
        """
        One iteration of poll: list sessions -> for each session list handles -> for each handle fetch handle_info
        and extract metrics into self.metrics and broadcast new datapoints.
        """
        try:
            sessions = await self.list_sessions()
        except Exception as e:
            logger.exception("Failed to list_sessions: %s", e)
            return

        for session in sessions:
            try:
                handles = await self.list_handles(session)
            except Exception:
                logger.exception("Failed to list_handles for session %s", session)
                continue

            for handle in handles:
                try:
                    info = await self.handle_info(session, handle)
                except Exception:
                    logger.exception("Failed to handle_info for %s/%s", session, handle)
                    continue

                # Extract metrics snapshot from 'info' (streams + optionally top-level stats)
                point = self._extract_metrics_point(info)
                if point:
                    key = (session, handle)
                    self.metrics[key].append(point)
                    # broadcast an event for this new metrics point to subscribers
                    await self._broadcast({"type": "metrics_point", "session_id": session, "handle_id": handle,
                                           "point": {"ts": point.ts, "values": point.values}})
        # end poll once

    def _extract_metrics_point(self, handle_info: Dict[str, Any]) -> Optional[MetricsPoint]:
        """
        Parse a handle_info response and build a MetricsPoint.
        This function is intentionally generic: Janus returns 'streams' with nested stats.
        We try to extract common metrics: bytes (in/out), packets (in/out), packets_lost, jitter, nacks, nack_count.
        If nothing found, return None.
        """
        ts = time.time()
        values: Dict[str, Any] = {}

        # Some top-level counters might exist (queued-packets, etc.)
        for top_field in ("queued-packets", "queued-rtp-packets"):
            if top_field in handle_info:
                values[top_field] = handle_info.get(top_field)

        streams = handle_info.get("streams") or []
        # Streams can contain one or more stream objects (in/out)
        for s in streams:
            # s typically contains keys like "ssrc", "direction", "stats" or RTCP fields
            direction = s.get("direction", "unknown")  # inbound/outbound
            prefix = f"{direction}" if direction else "stream"

            # Attempt to extract a common "stats" map
            stats = s.get("stats") or s.get("rtp_stats") or {}
            # keys we commonly expect (use .get to avoid KeyError)
            for k in ("bytes", "bytes_sent", "bytes_received", "packets", "packets_sent", "packets_received",
                      "packets_lost", "jitter", "nacks", "nack_requests", "nack_count"):
                if k in stats:
                    # normalize key names for frontend
                    normalized = f"{prefix}_{k}"
                    values[normalized] = stats.get(k)

            # some responses include 'bitrate' or 'bitrate_in/bitrate_out'
            for k in ("bitrate_in", "bitrate_out", "bitrate"):
                if k in s:
                    values[f"{prefix}_{k}"] = s.get(k)

            # If 'ssrc' present, store min details
            if "ssrc" in s:
                values[f"{prefix}_ssrc"] = s.get("ssrc")
            # codec info if present
            codec = s.get("codec") or s.get("codec_name")
            if codec:
                values[f"{prefix}_codec"] = codec

        # If no useful metrics found, return None
        if not values:
            return None
        return MetricsPoint(ts=ts, values=values)

    async def start_polling(self) -> None:
        """
        Start a background task that periodically polls Janus, collects metrics and broadcasts them.
        """
        if self._poller_task and not self._poller_task.done():
            return

        self._poller_task = self.loop.create_task(self._poll_loop())
        logger.info("Started poller task with interval %s", self.poll_interval)

    async def stop_polling(self) -> None:
        if self._poller_task:
            self._poller_task.cancel()
            self._poller_task = None

    async def _poll_loop(self) -> None:
        try:
            while self._running:
                await self._poll_once()
                await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            logger.debug("Poll loop cancelled")
        except Exception:
            logger.exception("Poll loop error")

    # Subscriber management for broadcast (used by FastAPI ws endpoint) -------------
    def subscribe(self, *, max_queue_size: int = 100) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self._broadcast_queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._broadcast_queues.discard(q)

    # Utility to fetch timeseries for a handle ------------------------------------------------
    def get_timeseries(
            self, session_id: int, handle_id: int, metric_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Return a list of dict points: [{"ts": <float>, "value": <number>, "values": {...}}, ...]
        If metric_key provided, returns only points having that value.
        """
        key = (session_id, handle_id)
        dq = self.metrics.get(key)
        if not dq:
            return []

        out = []
        for p in dq:
            if metric_key is not None:
                if metric_key in p.values:
                    out.append({"ts": p.ts, "value": p.values[metric_key], "values": p.values})
            else:
                out.append({"ts": p.ts, "values": p.values})
        return out


class MonitorFilter:
    def __init__(self, plugins_included: Optional[Set[str]] = None, only_publisher: bool = False,
                 room_ids: Optional[Set[str]] = None):
        self.plugins_included = plugins_included
        self.only_publisher = only_publisher
        self.room_ids = room_ids

    def allow_handle(self, handle_info: Dict[str, Any]) -> bool:
        """
        Decide whether a handle should be polled/persisted.
        handle_info: output from handle_info; expects at least 'plugin' and possibly 'streams' with 'direction' or 'role'
        """
        if self.plugins_included is not None:
            plugin = handle_info.get("plugin")
            if plugin not in self.plugins_included:
                return False

        # if room filtering applied (sometimes handle_info -> plugin_data -> {room})
        if self.room_ids:
            room = None
            plugin_data = handle_info.get("plugin_data") or {}
            # videoroom plugin often returns 'room' or 'room_id' in plugin_data
            room = plugin_data.get("room") or plugin_data.get("room_id")
            if room is not None and str(room) not in self.room_ids:
                return False

        if self.only_publisher:
            # try checking if handle indicates 'publisher'
            plugin_data = handle_info.get("plugin_data") or {}
            # many videoroom handle_info have "publisher" or "is_publisher" or role in 'streams'
            role = plugin_data.get("role") or plugin_data.get("is_publisher") or plugin_data.get("publisher")
            if role in (False, "subscriber", "listener"):
                return False
            # fallback: check streams and direction 'outbound' marking publisher outbound egress
            streams = handle_info.get("streams") or []
            # if there are outbound streams, likely a publisher
            if not any(s.get("direction") == "outbound" for s in streams):
                # not obviously a publisher -> skip
                return False
        return True


class JanusAdminMonitor(JanusBaseAdminMonitor):
    def __init__(self, *args, storage: Optional[TimescaleStorage] = None, max_reconnect_attempts: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self.storage = storage
        self._reconnect_lock = asyncio.Lock()
        self._max_reconnect_attempts = max_reconnect_attempts  # 0 = unlimited
        self._last_success: float = 0.0
        self._health_check_interval = 10.0
        self._health_task: Optional[asyncio.Task] = None
        self._filter: Optional[MonitorFilter] = None
        # throttle storage writes with semaphore to avoid db overload during storms
        self._storage_sem = asyncio.Semaphore(8)
        # in JanusAdminMonitorEnhanced.__init__
        self.last_event_ts: Dict[Tuple[int, int], float] = {}
        self.poll_fallback_window = 30.0  # seconds — skip polling handles with events in last 30s

    def set_filter(self, monitor_filter: MonitorFilter) -> None:
        self._filter = monitor_filter

    async def _ensure_connected(self):
        """
        Ensure _ws is connected; if not, attempt reconnect with exponential backoff.
        """
        async with self._reconnect_lock:
            if self._ws and not self.closed:
                return
            attempt = 0
            base = 0.5
            while True:
                attempt += 1
                try:
                    await self.connect()
                    # quick ping to validate
                    await self.ping()
                    self._last_success = time.time()
                    logger.info("Reconnected to Janus admin after %s attempts", attempt)
                    return
                except Exception as e:
                    logger.warning("Reconnect attempt %d failed: %s", attempt, e)
                    if self._max_reconnect_attempts and attempt >= self._max_reconnect_attempts:
                        raise RuntimeError("max reconnect attempts reached") from e
                    sleep = base * (2 ** (attempt - 1))
                    # jitter
                    sleep = sleep + random.uniform(0, min(1.0, sleep * 0.1))
                    await asyncio.sleep(min(sleep, 30.0))

    async def send_request(self, *args, **kwargs):
        # override to ensure connection
        if not self._ws or self.closed:
            await self._ensure_connected()
        res = await super().send_request(*args, **kwargs)
        self._last_success = time.time()
        return res

    async def start_polling(self):
        await super().start_polling()
        if not self._health_task or self._health_task.done():
            self._health_task = asyncio.create_task(self._health_loop())

    async def _health_loop(self):
        try:
            while self._running:
                # if last success older than threshold, try to reconnect
                if time.time() - self._last_success > (self._health_check_interval * 3):
                    logger.info("No successful response for a while; ensuring connection")
                    try:
                        await self._ensure_connected()
                    except Exception as e:
                        logger.exception("Health-triggered reconnect failed", exc_info=e)
                await asyncio.sleep(self._health_check_interval)
        except asyncio.CancelledError:
            return

    async def _poll_once(self):
        # ensure connected
        if not self._ws or self.closed:
            await self._ensure_connected()
        # reuse parent implementation but add filtering and storage writes
        sessions = await self.list_sessions()
        for session in sessions:
            handles = await self.list_handles(session)
            for handle in handles:
                # in _poll_once, before calling handle_info:
                if (session, handle) in self.last_event_ts and (
                        time.time() - self.last_event_ts[(session, handle)]) < self.poll_fallback_window:
                    # skip polling this handle because recent events arrived
                    continue
                info = await self.handle_info(session, handle)
                if self._filter and not self._filter.allow_handle(info):
                    continue
                point = self._extract_metrics_point(info)
                if point:
                    key = (session, handle)
                    self.metrics[key].append(point)
                    # broadcast
                    await self._broadcast({"type": "metrics_point", "session_id": session, "handle_id": handle,
                                           "point": {"ts": point.ts, "values": point.values}})
                    # persist to timescale if available
                    if self.storage:
                        # extract plugin, room_id, peer_id when possible
                        plugin = info.get("plugin")
                        plugin_data = info.get("plugin_data") or {}
                        room_id = plugin_data.get("room") or plugin_data.get("room_id")
                        peer_id = plugin_data.get("id") or plugin_data.get("peer_id")
                        # fire-and-forget with semaphore
                        asyncio.create_task(self._persist_point_safe(point, session, handle, plugin, room_id, peer_id))
        # done

    async def _persist_point_safe(self, point: MetricsPoint, session: int, handle: int, plugin: Optional[str],
                                  room_id: Optional[str], peer_id: Optional[str]):
        try:
            async with self._storage_sem:
                await self.storage.insert_metric(point.ts, session, handle, plugin, room_id, peer_id, point.values)
        except Exception as e:
            logger.exception("Failed to persist metrics point", exc_info=e)

    async def handle_event_handler_payload(self, payload: Dict[str, Any]):
        """
        Called by FastAPI when Janus EventHandler posts an event. Try to parse and persist or broadcast.
        """
        # event payload structure depends on your eventhandler configuration; adapt parsing accordingly
        # Example: payload may include session_id, handle_id, plugin, and stats
        session = payload.get("session_id")
        handle = payload.get("handle_id")
        plugin = payload.get("plugin")
        plugin_data = payload.get("plugin_data") or {}
        ts = payload.get("timestamp") or time.time()
        # when handling eventhandler payload, update last_event_ts:
        self.last_event_ts[(session, handle)] = time.time() # type: ignore
        # normalize metrics: assume payload['stats'] contains numeric fields
        metrics = payload.get("stats") or payload.get("metrics") or {}
        # broadcast
        await self._broadcast({"type": "eventhandler", "payload": payload})
        # persist
        if self.storage and metrics:
            await self._persist_point_safe(MetricsPoint(ts=ts, values=metrics), session, handle, plugin, # type: ignore
                                           plugin_data.get("room"), plugin_data.get("id"))
