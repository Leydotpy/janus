import asyncio
import inspect
import logging
import os
import socket
import traceback
from typing import Any, Callable, Iterable, Optional

import redis.asyncio as redis
from aiohttp import ClientSession
from aiohttp import web

from janus_api.conf import settings
from janus_api.session import WebsocketSession

# Configure module-level logger
logger = logging.getLogger(__name__)


def get_session(sid=None):
    if sid is None:
        return WebsocketSession()
    return WebsocketSession(session_id=sid)


# -----------------------------
# Janus Session manager - coordinates session life
# -----------------------------
class JanusSessionManager:
    """
    Manages Janus sessions with support for leadership election and session proxying.

    This class handles the lifecycle management of Janus sessions across distributed workers. It can operate in two modes:
    leader mode and follower mode. In leader mode, the class ensures a single leader exists within a distributed system,
    and the leader manages the Janus session as well as a proxy server for followers. Followers communicate with the leader
    via the proxy to interact with the Janus session.

    Methods:
        get_session(): Retrieves the current active session. If in follower mode, returns the session proxy connected
            to the leader.
        start(): Initiates the session management process. Depending on the configuration, it starts the leader elector
            and runs the corresponding session management loops.
        stop(): Stops session management activities, including terminating the leader elector, destroying sessions,
            and stopping the proxy server if active.
    """

    def __init__(self):
        self._session = None
        self._session_lock = asyncio.Lock()
        self._elector: Optional[RedisLeaderElector] = None
        self._proxy_server: Optional[LeaderProxyServer] = None
        self._proxy_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._stopped = asyncio.Event()

        # what the followers will use to talk to leader
        self._follower_proxy: Optional[SessionProxy] = None

    def get_session(self):
        return self._session or self._follower_proxy

    async def start(self):
        """
        Starts the main process for leader election or local session creation.

        This coroutine handles the initialization of the service based on the
        configuration provided. If the application is set to run in leader mode, it
        initiates a leader election mechanism using Redis for distributed coordination.
        Otherwise, it creates a local session for the worker.

        Attributes:
            settings (dict): Configuration settings for the service. Includes relevant
                options such as LEADER_MODE, REDIS_URL, LEADER_LOCK_KEY,
                LEADER_LOCK_TTL, and LEADER_REFRESH_INTERVAL.

        Raises:
            asyncio.CancelledError: Raised if the tasks are cancelled during the
                execution of the process.
        """
        self._stopped.clear()
        leader_mode = bool(getattr(settings, "LEADER_MODE"))

        if leader_mode:
            # start leader elector
            self._elector = RedisLeaderElector(
                redis_url=getattr(settings, "REDIS_URL"),
                lock_key=getattr(settings, "LEADER_LOCK_KEY"),
                lock_ttl=getattr(settings, "LEADER_LOCK_TTL"),
                refresh_interval=getattr(settings, "LEADER_REFRESH_INTERVAL"),
            )
            await self._elector.start()
            # start monitor loop
            self._monitor_task = asyncio.create_task(self._leader_mode_loop())
        else:
            # Not leader-mode: just create a local session for this worker
            await self._create_local_session()
            # start lightweight monitor to recreate on failure
            self._monitor_task = asyncio.create_task(self._local_monitor_loop())

    async def stop(self):
        """
        Stops the currently running tasks, cancels ongoing operations, and
        cleans up associated resources. This method ensures the orderly shutdown
        of all components to free up resources and avoid potential memory leaks.

        Raises:
            asyncio.CancelledError: If the cancellation of the monitor task
            raises this error, it is caught and handled internally.
        """
        self._stopped.set()
        # cancel monitor
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        # stop elector
        if self._elector:
            await self._elector.stop()
            self._elector = None
        # stop proxy server if running
        if self._proxy_server:
            await self._proxy_server.stop()
            self._proxy_server = None
        if self._follower_proxy:
            await self._follower_proxy.close()
            self._follower_proxy = None
        # destroy local session if present
        if self._session is not None:
            try:
                destroy = getattr(self._session, "destroy", None)
                if destroy:
                    maybe = destroy()
                    if asyncio.iscoroutine(maybe):
                        await maybe
            except Exception:
                logger.exception("Failed to destroy session during stop")
            self._session = None

    # -------------------
    # local session management
    # -------------------
    async def _create_local_session(self):
        async with self._session_lock:
            if self._session is not None:
                return
            logger.info("Creating janus session for worker pid=%s", os.getpid())
            # janus-api helper
            session = get_session()
            await session.create()
            self._session = session
            logger.info("Janus session created for worker pid=%s", os.getpid())

    async def _destroy_local_session(self):
        async with self._session_lock:
            if self._session is None:
                return
            try:
                destroy = getattr(self._session, "destroy", None)
                if destroy:
                    maybe = destroy()
                    if asyncio.iscoroutine(maybe):
                        await maybe
            except Exception as e:
                logger.exception("Error destroying local session", exc_info=e)
            self._session = None

    async def _local_monitor_loop(self):
        backoff = float(getattr(settings, "MONITOR_BACKOFF", 5))
        while not self._stopped.is_set():
            try:
                if self._session is None:
                    await self._create_local_session()
                await asyncio.sleep(backoff)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Local monitor loop error", exc_info=e)
                await asyncio.sleep(backoff)

    # -------------------
    # leader-mode loop
    # -------------------
    async def _leader_mode_loop(self):
        """Continuously observe election state and either become leader (create session + proxy)
        or become follower (destroy local session and connect to leader proxy).
        """
        proxy_host = getattr(settings, "LEADER_PROXY_HOST")
        proxy_port = getattr(settings, "LEADER_PROXY_PORT")
        proxy_url = f"http://{proxy_host}:{proxy_port}/rpc"
        allowed = getattr(settings, "ALLOWED_PROXY_METHODS", [])

        while not self._stopped.is_set():
            try:
                if self._elector and self._elector.is_leader():
                    # if elector exists and says leader: ensure we have a local session + proxy server
                    if self._session is None:
                        await self._create_local_session()
                    if self._proxy_server is None:
                        # start leader proxy bound to configured host/port
                        self._proxy_server = LeaderProxyServer(lambda: self._session, host=proxy_host, port=proxy_port,
                                                               allowed_methods=allowed)
                        await self._proxy_server.start()
                    # if followers exist they will build proxies pointing here
                else:
                    # follower: destroy any local session, and ensure follower proxy exists
                    if self._session is not None:
                        await self._destroy_local_session()
                    if self._follower_proxy is None:
                        # follower will contact leader proxy. Use configured URL
                        self._follower_proxy = SessionProxy(proxy_url)
                await asyncio.sleep(getattr(settings, "LEADER_REFRESH_INTERVAL", 5))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Error in leader mode loop", exc_info=exc)
                await asyncio.sleep(getattr(settings,"MONITOR_BACKOFF", 5))


# -----------------------------
# Leader election helper
# -----------------------------
class RedisLeaderElector:
    """Very small leader election using redis async lock.
    - Acquire a redis lock key with TTL.
    - Keep refreshing the lock periodically.
    - When canceled, releases the lock.

    Note: This is a simple approach. For production consider tried-and-tested libraries
    if you need stronger guarantees (e.g. etcd, consul, zookeeper, or RedLock variants).
    """

    def __init__(
            self,
            redis_url: str,
            lock_key: str = "janus:leader",
            lock_ttl: int = 10,
            refresh_interval: int = 5,
    ):
        self._redis = redis.from_url(redis_url)
        self.lock_key = lock_key
        self.lock_ttl = lock_ttl
        self.refresh_interval = refresh_interval

        self._is_leader = False
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def start(self):
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._stop.set()
        task = self._task
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        # release if we hold it
        if self._is_leader:
            try:
                await self._redis.delete(self.lock_key)
            except Exception as e:
                logger.exception("Failed to delete leader lock on stop", exc_info=e)

    async def _run(self):
        # loop attempting to acquire lock and then refreshing
        try:
            while not self._stop.is_set():
                try:
                    # Try to set the key if not exists with ttl
                    got = await self._redis.set(self.lock_key, socket.gethostname(), nx=True, ex=self.lock_ttl)
                    if got:
                        # we are leader
                        if not self._is_leader:
                            logger.info("Acquired leader lock: %s", self.lock_key)
                        self._is_leader = True
                        # refresh loop while we remain leader
                        # Sleep shorter than TTL and refresh repeatedly
                        while not self._stop.is_set():
                            await asyncio.sleep(self.refresh_interval)
                            try:
                                # extend TTL only if we still hold the key value (simple check)
                                val = await self._redis.get(self.lock_key)
                                if val is None:
                                    # lock lost
                                    logger.warning("Leader lock lost (no value)")
                                    self._is_leader = False
                                    break
                                # set expire to TTL again
                                await self._redis.expire(self.lock_key, self.lock_ttl)
                            except Exception as exc:
                                logger.exception("Error refreshing leader lock", exc_info=exc)
                                # on error, let the outer loop retry
                                self._is_leader = False
                                break
                    else:
                        # not leader; sleep and retry
                        if self._is_leader:
                            logger.info("No longer leader")
                        self._is_leader = False
                        await asyncio.sleep(self.refresh_interval)
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.exception("Leader elector error", exc_info=exc)
                    await asyncio.sleep(self.refresh_interval)
        finally:
            self._is_leader = False

    def is_leader(self) -> bool:
        return self._is_leader


# -----------------------------
# Leader proxy (aiohttp) - lightweight JSON RPC
# -----------------------------
class LeaderProxyServer:
    """Small aiohttp server that forwards calls to the local Janus session object.
    Security note: it binds to a loopback address by default. Do not expose it publicly.
    Only allowed methods are callable via the proxy.
    """

    def __init__(self, session_getter: Callable[[], Any], host: str = "127.0.0.1", port: int = 5901,
                 allowed_methods: Optional[Iterable[str]] = None):
        self._session_getter = session_getter
        self.host = host
        self.port = port
        self.allowed_methods = set(allowed_methods or {})
        self._runner: Optional[web.AppRunner] = None

    async def start(self):
        app = web.Application()
        app.router.add_post("/rpc", self._handle_rpc)
        self._runner = web.AppRunner(app)
        await self._runner.setup()  # type: ignore
        site = web.TCPSite(self._runner, host=self.host, port=self.port)  # type: ignore
        await site.start()
        logger.info("Leader proxy listening on %s:%s", self.host, self.port)

    async def stop(self):
        if self._runner is None:
            return
        try:
            await self._runner.cleanup()
        except Exception as exc:
            logger.exception("Error stopping proxy runner", exc_info=exc)

    async def _handle_rpc(self, request: web.Request):
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        method = payload.get("method")
        params = payload.get("params", [])
        if method not in self.allowed_methods:
            return web.json_response({"error": "method not allowed"}, status=403)

        session = self._session_getter()
        if session is None:
            return web.json_response({"error": "session not available"}, status=503)

        # attribute lookup
        attr = getattr(session, method, None)
        if attr is None:
            return web.json_response({"error": "method not found on session"}, status=404)

        try:
            # call method; support coroutine or normal callable
            result = attr(*params) if not inspect.iscoroutinefunction(attr) else await attr(*params)
            # if result is not JSON serializable, attempt to convert
            return web.json_response({"result": result})
        except Exception as exc:
            logger.exception("Error in proxy method %s", method)
            return web.json_response({"error": str(exc), "trace": traceback.format_exc()}, status=500)


# -----------------------------
# SessionProxy for followers
# -----------------------------
class SessionProxy:
    """Object that forwards calls to leader proxy via HTTP JSON RPC.

    Example: await session_proxy.create()
    or: await session_proxy.plugin_request(plugin, data)

    It will call POST /rpc with {method: <name>, params: [..]}
    """

    def __init__(self, proxy_url: str, timeout: float = 5.0):
        self.proxy_url = proxy_url
        self._client: Optional[ClientSession] = None
        self.timeout = timeout

    async def _ensure_client(self):
        if self._client is None:
            self._client = ClientSession()

    async def _rpc(self, method: str, params: Optional[list] = None):
        await self._ensure_client()
        payload = {"method": method, "params": params or []}
        try:
            async with self._client.post(self.proxy_url, json=payload, timeout=self.timeout) as resp:
                data = await resp.json()
                if resp.status != 200:
                    raise RuntimeError(f"Proxy error {resp.status}: {data}")
                if "error" in data and data["error"] is not None:
                    raise RuntimeError(f"Proxy error: {data['error']}")
                return data.get("result")
        except Exception:
            logger.exception("Proxy RPC failed")
            raise

    def __getattr__(self, name: str):
        # return a coroutine function that wraps _rpc
        async def _caller(*args):
            return await self._rpc(name, list(args))

        return _caller

    async def close(self):
        if self._client:
            await self._client.close()
            self._client = None
