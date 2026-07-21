import asyncio
import logging
import typing
from typing import Callable, Any
from typing import Optional, Dict

from janus_api.core.utils import dummy_fn, _uuid_str
from janus_api.lib.plugins.base import Plugin

logger = logging.getLogger(__name__)


# -------------------------
# Option 2: Persistent admin plugin manager
# -------------------------
class PersistentJanusPluginManager:
    """
    Process-global manager that keeps one transient "system" plugin attached and re-uses it.
    It reconnects on failures and serializes attach/detach to avoid races.
    """

    _instance: Optional["PersistentJanusPluginManager"] = None

    def __init__(self, *, on_event: Callable[[Any], Any] = None):
        # holds the attached plugin object (from janus_api.plugins.Plugin)
        self._plugin: Optional[Plugin] = None
        self._lock = asyncio.Lock()
        # time when plugin was attached (optional)
        self._attached_at: Optional[float] = None
        default_on_event = lambda x: logger.info(f"[EVENT RECEIVED]: {x}")
        self._on_event = on_event or default_on_event

    @classmethod
    def instance(cls) -> "PersistentJanusPluginManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance  # type: ignore

    async def _ensure_attached(self, room_hint: Optional[str] = None) -> Plugin:
        """
        Ensure we have a live attached plugin and return it.
        Attaches a new plugin if none or if the existing plugin failed.
        """
        async with self._lock:
            # quick check
            if self._plugin is not None:
                try:
                    # optionally check plugin health via a lightweight call (exists with short timeout)
                    try:
                        await asyncio.wait_for(getattr(self._plugin, "exists", dummy_fn)(), timeout=2.0)
                        return self._plugin
                    except asyncio.TimeoutError:
                        logger.warning("Persistent plugin exists() timed out; will reattach")
                    except AttributeError:
                        logger.warning("Persistent plugin has no attribute 'exists'; will reattach")
                    except Exception as exc:
                        logger.warning("Persistent plugin health check failed; reattaching", exc_info=exc)
                except Exception as exception:
                    # proceed to reattach
                    logger.warning("Persistent plugin health check failed; reattaching", exc_info=exception)

            # attach a new plugin
            try:
                from janus_api.conf import Janus
                username = f"system-persistent{('-' + str(room_hint)) if room_hint else ''}"
                plugin = await Plugin(
                    identifier="publisher",
                    username=username,
                    session=Janus.get_session(),
                    room=room_hint or _uuid_str()[:5],
                    on_rx_event=self._on_event
                ).attach(

                )
                self._plugin = plugin  # type: ignore
                self._attached_at = asyncio.get_event_loop().time()
                logger.info("[PLUGIN ATTACHED]: Persistent Janus plugin attached (id=%s)", getattr(plugin, "id", None))
                return plugin  # type: ignore
            except Exception as exc:
                logger.exception("Failed to attach persistent janus plugin: %s", exc)
                # ensure plugin cleared
                self._plugin = None
                self._attached_at = None
                raise

    async def exists(self, room_id: str) -> bool:
        """
        Use the persistent plugin to check existence; attach first if necessary.
        """
        plugin = await self._ensure_attached(room_hint=room_id)
        try:
            # small timeout for exists check
            return bool(await asyncio.wait_for(getattr(plugin, "exists", dummy_fn)(), timeout=3.0))
        except asyncio.TimeoutError:
            logger.warning("Persistent plugin.exists() timed out for room %s", room_id)
            return False
        except AttributeError:
            logger.warning("Persistent plugin has no attribute 'exists'")
            return False
        except Exception as exc:
            logger.exception("Persistent plugin.exists() failed for room %s: %s", room_id, exc)
            # clear plugin so next call reattaches
            await self._safe_detach()
            return False

    async def create(self, room_id: str, create_kwargs: Optional[Dict[str, typing.Any]] = None) -> None:
        """
        Create a room using the persistent plugin (attach if needed).
        """
        plugin = await self._ensure_attached(room_hint=room_id)
        create_kwargs = create_kwargs or {}
        create_kwargs.setdefault("room", room_id)
        try:
            await asyncio.wait_for(getattr(plugin, "create", dummy_fn)(**create_kwargs), timeout=12.0) # type: ignore[arg-type]
            # verify quickly
            ok = await asyncio.wait_for(getattr(plugin, "exists", dummy_fn)(), timeout=3.0)
            if not ok:
                raise RuntimeError("create did not produce a visible room")
            # success
            return
        except Exception as exc:
            logger.exception("Persistent plugin.create failed for %s: %s", room_id, exc)
            # detach plugin to force reattach next time
            await self._safe_detach()
            raise

    async def _safe_detach(self) -> None:
        """
        Try to detach and clear plugin reference.
        """
        if self._plugin is None:
            return
        try:
            await self._plugin.detach()
        except Exception as exc:
            logger.exception("Failed to detach persistent plugin", exc_info=exc)
        finally:
            self._plugin = None
            self._attached_at = None

    async def close(self) -> None:
        """
        Close the manager and detach plugin; call on process shutdown if desired.
        """
        async with self._lock:
            await self._safe_detach()
