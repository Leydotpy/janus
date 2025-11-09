"""WebsocketSession keepalive improvements."""
import asyncio
from typing import Optional

from janus_api.models.request import CreateSessionRequest, DestroySessionRequest, KeepAliveRequest
from janus_api.session.base import AbstractBaseSession
import logging

logger = logging.getLogger("janus.session")


class WebsocketSession(AbstractBaseSession):
    __slots__ = (
        "_ka_task",
        "_ka_interval",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._ka_task: Optional[asyncio.Task] = None
        self._ka_interval: int = 15

    async def create(self):
        # guard for some Django dev server double-import behaviors
        await self._setup()
        request = CreateSessionRequest(janus="create")
        response = await self.send(request)
        assert response.janus == "success"
        self.id = response.data.id
        # start keepalive background task
        self._ka_task = asyncio.create_task(self._keepalive_loop())
        return self

    async def _keepalive_loop(self):
        if not self.id:
            return
        try:
            while True:
                req = KeepAliveRequest(janus="keepalive", session_id=self.id)
                try:
                    await self.send(req)
                except Exception as e:
                    logger.warning("Keepalive send failed: %s", e)
                await asyncio.sleep(self._ka_interval)
        except asyncio.CancelledError:
            return

    async def destroy(self):
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

