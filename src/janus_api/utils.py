import asyncio
import typing
import uuid
from functools import partial
from typing import Coroutine
from asgiref.sync import async_to_sync

DEFAULT_UUID_LENGTH = 6


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
