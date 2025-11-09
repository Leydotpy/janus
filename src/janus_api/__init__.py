import threading

from asgiref.sync import async_to_sync

from janus_api.utils import run_coroutine_task
from janus_api.plugins import Plugin
from janus_api.session import WebsocketSession


def get_session(sid=None):
    if sid is None:
        return WebsocketSession()
    return WebsocketSession(session_id=sid)


def setup():
    def _create():
        run_coroutine_task(get_session().create)

    thread = threading.Thread(target=_create, daemon=True)
    thread.start()

def teardown() -> None:
    async_to_sync(get_session().destroy)()


__all__ = ["Plugin", "get_session", "setup", "teardown"]
