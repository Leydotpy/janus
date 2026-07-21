# Admin HTTP conf in settings (optional)
# settings.JANUS_ADMIN_URL = "http://janus-host:7088/admin"
# settings.JANUS_ADMIN_API_KEY = "..."  # optional header/token if your admin endpoint requires auth
import importlib
import logging
from typing import Optional, Dict, Any

import httpx
from asgiref.sync import sync_to_async
from janus_api.conf import settings
from decouple import config

logger = logging.getLogger(__name__)

cache_dir = getattr(settings, "JANUS_ADMIN_CACHE_DIR", "cache")
_JANUS_ROOM_CACHE_TTL = getattr(settings, "JANUS_ROOM_CACHE_TTL", 30)
JANUS_ADMIN_API_KEY = getattr(settings, "JANUS_ADMIN_API_KEY", None)
JANUS_ADMIN_URL = getattr(settings, "JANUS_ADMIN_URL", "http://janus-host:7088/admin")


try:
    cache = importlib.import_module(cache_dir)
except Exception as e:
    logger.exception(f"Failed to load {cache_dir}: {str(e)}", exc_info=e)
    cache = None


# -------------------------
# Option 1: Janus Admin HTTP API (cheapest)
# -------------------------
async def exists(room_id: str) -> bool:
    """
    Query the Janus admin HTTP API to check if a room exists.
    Returns True if present, False otherwise. Raise on unrecoverable errors only if desired.
    """
    admin_url = JANUS_ADMIN_URL
    if not admin_url:
        return False

    # try cache first
    cache_key = f"janus_room_admin_exists:{room_id}"
    try:
        cached = await sync_to_async(getattr(cache, "get", lambda k: None))(cache_key)
        if cached:
            return True
    except Exception as exc:
        logger.debug("cache.get failed for janus admin exists check (non-fatal)", exc_info=exc)

    # Example admin endpoints vary — try endpoint patterns:
    # 1) GET {admin_url}/rooms
    # 2) GET {admin_url}/room/{room_id}
    headers = {}
    api_key = JANUS_ADMIN_API_KEY
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # prefer the more specific room endpoint first
    room_endpoint = f"{admin_url.rstrip('/')}/room/{room_id}"
    list_endpoint = f"{admin_url.rstrip('/')}/rooms"

    async with httpx.AsyncClient(timeout=3.0) as client:
        # try /room/{id}
        try:
            r = await client.get(room_endpoint, headers=headers)
            if r.status_code == 200:
                # assume success body indicates existence; exact shape depends on admin API
                await sync_to_async(getattr(cache, "store", lambda *a, **k: None))(cache_key, True,
                                                                                   _JANUS_ROOM_CACHE_TTL)
                return True
            elif r.status_code == 404:
                return False
        except httpx.RequestError:
            logger.debug("janus admin /room/{id} request failed; trying rooms list fallback")

        # fallback: fetch rooms list and search (more expensive)
        try:
            r = await client.get(list_endpoint, headers=headers)
            if r.status_code == 200:
                data = r.json()
                # data shape is implementation dependant; try common shapes
                # if data is dict with 'rooms' key:
                rooms = data.get("rooms") if isinstance(data, dict) else data
                if rooms:
                    # rooms might be a list of dicts with keys 'room' or 'id'
                    for entry in rooms:  # type: ignore
                        if isinstance(entry, dict):
                            if str(entry.get("room") or entry.get("id", "")) == str(room_id):
                                await sync_to_async(getattr(cache, "store", lambda *a, **k: None))(cache_key, True,
                                                                                                   _JANUS_ROOM_CACHE_TTL)
                                return True
                        else:
                            if str(entry) == str(room_id):
                                await sync_to_async(getattr(cache, "store", lambda *a, **k: None))(cache_key, True,
                                                                                                   _JANUS_ROOM_CACHE_TTL)
                                return True
                return False
        except httpx.RequestError as exc:
            logger.exception("Janus admin HTTP request failed: %s", exc)
            # don't raise here — allow fallback to plugin approaches
            return False

    return False


async def create(room_id: str, create_kwargs: Optional[Dict[str, Any]] = None) -> None:
    """
    Create a room using the admin HTTP endpoint. Raises RuntimeError on failure.
    Returns None on success.
    """
    admin_url = JANUS_ADMIN_URL
    if not admin_url:
        raise RuntimeError("JANUS_ADMIN_URL not configured")

    headers = {}
    api_key = JANUS_ADMIN_API_KEY
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    create_endpoint = f"{admin_url.rstrip('/')}/room"
    payload = {"room": room_id}
    if create_kwargs:
        payload.update(create_kwargs)

    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            r = await client.post(create_endpoint, json=payload, headers=headers)
        except httpx.RequestError as exc:
            logger.exception("Janus admin create request failed for %s: %s", room_id, exc)
            raise RuntimeError("Janus admin create failed") from exc

        if r.status_code not in (200, 201):
            logger.exception("Janus admin create returned unexpected status %s body=%s", r.status_code, r.text)
            raise RuntimeError(f"Janus admin create failed (status={r.status_code})")

    # warm the cache
    cache_key = f"janus_room_admin_exists:{room_id}"
    await sync_to_async(getattr(cache, "store", lambda *a, **k: None))(cache_key, True, _JANUS_ROOM_CACHE_TTL)
