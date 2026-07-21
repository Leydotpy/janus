import asyncio
import logging
from typing import Optional
from fastapi import Request

from janus_api.core import PersistentJanusPluginManager

from janus_api.api.rest.manager._models import ManagerHealth, ManagerReady

logger = logging.getLogger(__name__)


async def _safe_exists_check(manager: PersistentJanusPluginManager, room_id: str, timeout: float = 2.0):
    """
    check if a manager exists \n
    Call manager.exists(room_id) safely with timeout; return dict with result or error
    """

    try:
        okay = await asyncio.wait_for(manager.exists(room_id), timeout=timeout)
        return {"exists": bool(okay)}
    except asyncio.TimeoutError:
        return {"exists": False, "error": "timeout"}
    except Exception as e:
        logger.exception("Error during exist check for room %s: %s", room_id, e, exc_info=e)
        return {"exists": False, "error": str(e)}


async def _get_manager_health(request: Request, room: Optional[str] = None, timeout: float = 2.0):
    ppm = request.state.ppm
    plugin = getattr(ppm, "_plugin", None)
    attached = plugin is not None
    plugin_id = getattr(plugin, "id", None)
    attached_at = getattr(ppm, "_attached_at", None)
    attached_since_seconds: Optional[float] = None
    if attached_at is not None:
        try:
            attached_since_seconds = asyncio.get_event_loop().time() - attached_at  # type: ignore
        except Exception as e:
            logger.exception("Error getting time from plugin %s: %s", plugin_id, e, exc_info=e)
            attached_since_seconds = None

    sample_room_check = None
    if room:
        sample_room_check = await _safe_exists_check(ppm, room, timeout=timeout)
    return ManagerHealth(
        service="Janus",
        attached=bool(attached),
        plugin_id=plugin_id,
        attached_since=attached_since_seconds,
        sample_room_check=sample_room_check,
    )


async def check_ready(request: Request, room: Optional[str] = None, timeout: float = 3.0):
    ppm = request.state.ppm
    try:
        if getattr(ppm, "_plugin", None) is not None:
            if room:
                check = await _safe_exists_check(ppm, room, timeout=timeout)
                if check.get("exists"):
                    return ManagerReady(ready=True, detail="persistent plugin healthy, room exists")
                return ManagerReady(ready=False, detail=f"room '{room}' does not exist")
            return ManagerReady(ready=True, detail="persistent plugin attached")
        else:
            try:
                await asyncio.wait_for(ppm._ensure_attached(), timeout=timeout)
                return ManagerReady(ready=True, detail="persistent plugin attached for readiness")
            except asyncio.TimeoutError:
                return ManagerReady(ready=False, detail="timeout attaching persistent plugin")
            except Exception as exc:
                logger.exception("Readiness attach attempt failed: %s", exc, exc_info=exc)
                return ManagerReady(ready=False, detail="unexpected error", error=str(exc))
    except Exception as e:
        logger.exception("Unexpected readiness check failure: %s", e, exc_info=e)
        return ManagerReady(ready=False, detail="unexpected error", error=str(e))
