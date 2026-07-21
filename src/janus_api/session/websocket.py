"""
WebsocketSession class provides functionality to manage and handle session interactions
with the Janus WebSocket API, including creation, maintenance through keepalive tasks,
and destruction.

The class is derived from AbstractBaseSession and implements asynchronous methods
for session lifecycle management (create, destroy), as well as a background task
to periodically send keepalive messages to ensure the session remains active.
"""
import asyncio
from typing import Optional

from janus_api.models.request import CreateSessionRequest, DestroySessionRequest, KeepAliveRequest
from janus_api.session.base import AbstractBaseSession
import logging


logger = logging.getLogger(__name__)


class WebsocketSession(AbstractBaseSession):
    """
    Manages a WebSocket session for communication with a Janus server.

    This class provides functionality to create, manage, and destroy a WebSocket
    session with a Janus server. It supports sending periodic "keepalive" messages
    to maintain the session active and can cleanly handle session termination.

    Attributes:
        id (Optional[int]): The current session ID assigned by the Janus server,
            or None if the session is not active.

    Methods:
        create: Initializes and establishes a new session with the Janus server.
        destroy: Terminates the active session and cleans up associated resources.
    """
    __slots__ = (
        "_ka_task",
        "_ka_interval",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._ka_task: Optional[asyncio.Task] = None
        self._ka_interval: int = 15

    async def create(self):
        """
        Creates a new session and initiates a keepalive background task.

        This method setups the session, sends a request to create a new session, and processes the response
        to confirm session creation. Once the session is successfully created, it logs the session ID and starts
        a background task for session keepalive.

        Raises:
            AssertionError: If the response indicates failure to create the session.
        """
        await self._setup()
        request = CreateSessionRequest(janus="create")
        response = await self.send(request)
        if response.janus != "success" or not hasattr(response, "data"):
            raise RuntimeError(f"Session creation failed with Janus response '{response.janus}'.")
        self.id = response.data.id
        logger.info(f"Session created::{self.id}")
        # start keepalive background task
        self._ka_task = asyncio.create_task(self._keepalive_loop(), name=f"janus-ka-{self.id}")

    async def _keepalive_loop(self):
        """
        Coroutine that manages the keepalive loop for a session.

        This coroutine continuously sends keepalive requests for a session to ensure
        its activity. It operates in an infinite loop, interrupted only by external
        cancellation or unrecoverable errors. Each iteration includes sending a keepalive
        request and sleeping for a specified interval. Upon encountering exceptions,
        it logs appropriate messages and handles specific errors.

        Attributes
        ----------
        id : str
            The session identifier used to reference the current session.
        _ka_interval : float
            Interval in seconds between successive keepalive requests.

        Raises
        ------
        asyncio.CancelledError
            Raised when the coroutine is explicitly cancelled through external mechanisms.
        Exception
            Raised for any unexpected errors within the keepalive loop.

        Warnings
        --------
        If session ID is absent, the keepalive loop is exited immediately as no session
        can be maintained without identifying information.
        """
        logger.info("keepalive loop started for session %s", self.id)
        if not self.id:
            logger.warning("keepalive: no session id; exiting")
            return
        try:
            while True:
                req = KeepAliveRequest(janus="keepalive", session_id=self.id)
                try:
                    logger.info("keepalive: sending for session %s tx=%s", self.id, getattr(req, "transaction", None))
                    # protect send with timeout so it can't block forever
                    await asyncio.wait_for(self.send(req), timeout=10)
                    logger.info("keepalive: send returned for session %s", self.id)
                except asyncio.TimeoutError:
                    logger.warning("keepalive: send timed out for session %s", self.id)
                except Exception as e:
                    logger.warning("keepalive send failed for session %s: %s", self.id, e)
                await asyncio.sleep(self._ka_interval)
        except asyncio.CancelledError:
            logger.info("keepalive cancelled for session %s", self.id)
            raise
        except Exception as exc:
            logger.exception("unexpected error in keepalive loop for session %s", self.id, exc_info=exc)

    async def destroy(self):
        """
        Destroys the current session and cleans up associated resources.

        This method is responsible for properly closing a session by sending a destroy
        request to the server and cleaning up any associated tasks or resources. It
        ensures that any ongoing keep-alive tasks are canceled and completed before
        finalizing the destruction process.

        Raises:
            asyncio.CancelledError: If the associated keep-alive task is canceled during cleanup.
        """
        if self.id:
            message = DestroySessionRequest(janus="destroy", session_id=self.id)
            await self.send(message)
            self.id = None
        if self._ka_task:
            self._ka_task.cancel()
            try:
                await self._ka_task
            except asyncio.CancelledError:
                pass
            self._ka_task = None
        await super().destroy()

