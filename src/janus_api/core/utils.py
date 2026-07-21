import asyncio
import logging
import typing
import uuid
from functools import partial
from typing import Coroutine
from typing import Optional

from asgiref.sync import async_to_sync

from janus_api.models import JanusResponse

logger = logging.getLogger(__name__)

DEFAULT_UUID_LENGTH = 6


async def dummy_fn(*args, **kwargs):
    raise AttributeError("Method not implemented in object")


async def _extract_participant_id_from_response(response: JanusResponse) -> Optional[str]:
    """Try common shapes: response.plugindata.data.id, response.data.id, dict forms."""
    plugindata = getattr(response, "plugindata", None)
    if plugindata is not None:
        data = getattr(plugindata, "data", None)
        if data is not None and hasattr(data, "id"):
            return data.id

    # dict-like
    try:
        pd = response.get("plugindata", {})
        d = pd.get("data", {})
        if "id" in d:
            return d["id"]
    except Exception:
        pass
    return None


async def _extract_plugin_id_from_response(response: JanusResponse) -> Optional[str]:
    data = getattr(response, "data", None)
    if data is not None and hasattr(data, "id"):
        return data.id

    try:
        d2 = response.get("data", {})
        if "id" in d2:
            return d2["id"]
    except Exception:
        pass
    return None


def _uuid_str() -> str:
    return str(uuid.uuid4())


def run_coroutine_task[T](coro: typing.Callable[[], Coroutine[typing.Any, typing.Any, T]]):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    asyncio.ensure_future(coro(), loop=loop)
    loop.run_forever()


def sync_call_coroutine[T](
        coro: typing.Callable[[], Coroutine[typing.Any, typing.Any, T]],
        *args,
        **kwargs
) -> T:
    return partial(async_to_sync, coro)(*args, **kwargs)


def generate_short_uuid(length: int = DEFAULT_UUID_LENGTH) -> str:
    return str(uuid.uuid4())[:length]
