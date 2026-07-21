import logging
import threading
from typing import Optional, TYPE_CHECKING

from asgiref.sync import async_to_sync

from janus_api.core.utils import run_coroutine_task

if TYPE_CHECKING:
    from janus_api.servers import JanusSessionManager

logger = logging.getLogger(__name__)


# -----------------------------
# Global accessor for request middleware
# -----------------------------
class Janus:
    """Simple global accessor so Django middleware can read session/proxy objects.
    The lifespan wrapper must call JanusGlobal.set_manager(manager) during startup.
    """

    _manager = None

    @classmethod
    def set_manager(cls, manager: JanusSessionManager) -> None:
        cls._manager = manager

    @classmethod
    def get_manager(cls) -> Optional[JanusSessionManager]:
        return cls._manager

    @classmethod
    def get_session(cls):
        manager = cls.get_manager()
        if manager is None:
            return None
        return manager.get_session()

    @classmethod
    def setup(cls):
        def _create():
            run_coroutine_task(cls.get_session().create)

        thread = threading.Thread(target=_create, daemon=True)
        thread.start()

    @classmethod
    def teardown(cls) -> None:
        async_to_sync(cls.get_session().destroy)()
