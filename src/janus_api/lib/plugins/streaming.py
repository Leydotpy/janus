from typing import Unpack, Optional, List, Literal, Any

from janus_api.models.base import Jsep
from janus_api.models.streaming import (
    MountPoint,
    ListRequest,
    DestroyRequest,
    CreateRequest,
    InfoRequest,
    WatchRequest,
    RecordingRequest,
    RecordingMedia,
    EditRequest,
    EnableRequest,
    DisableRequest,
    KickAllRequest,
    StartRequest,
    PauseRequest,
    StopRequest,
    SwitchRequest,
    ConfigureRequest,
    ConfigureStream,
)
from janus_api.lib.plugins.base import Plugin, PluginOptions


class StreamingPlugin(Plugin):
    name = "janus.plugin.streaming"
    identifier = "streaming"

    __slots__ = (
        "__mountpoint",
        "__admin_key",
    )

    def __init__(self, *, mountpoint: str | int | None = None, admin_key: Optional[str] = None, plugin_id: Optional[str] = None,
                 session=None, **kwargs: Unpack[PluginOptions]):
        super().__init__(
            plugin_id=plugin_id,
            session=session,
            **kwargs
        )

        self.__mountpoint = mountpoint
        self.__admin_key = admin_key

    @property
    def mountpoint(self):
        return self.__mountpoint

    def _resolve_mountpoint_id(self, mountpoint_id: int | str | None = None) -> int:
        target = mountpoint_id if mountpoint_id is not None else self.__mountpoint
        if target is None:
            raise ValueError("mountpoint ID is required when the plugin is not bound to a mountpoint")
        return int(target)

    async def list(self):
        return await self.send(ListRequest())

    async def info(self, secret: str | None = None, *, mountpoint_id: int | str | None = None):
        info = InfoRequest(id=self._resolve_mountpoint_id(mountpoint_id), secret=secret)
        return await self.send(info)

    async def create(
            self,
            *,
            admin_key: str | None = None,
            **kwargs: Unpack[MountPoint]
    ):
        default_admin_key = admin_key or self.__admin_key
        payload = CreateRequest(**kwargs, admin_key=default_admin_key)
        return await self.send(payload)

    async def destroy(
            self,
            *,
            mountpoint_id: int | str | None = None,
            secret: str | None = None,
            permanent: bool = False,
    ):
        request = DestroyRequest(
            id=self._resolve_mountpoint_id(mountpoint_id),
            permanent=permanent,
            secret=secret,
        )
        return await self.send(request)

    async def recording(
            self,
            action: Literal["start", "stop"],
            media: List[RecordingMedia],
            *,
            mountpoint_id: int | str | None = None,
    ):
        return await self.send(
            RecordingRequest(
                action=action,
                id=self._resolve_mountpoint_id(mountpoint_id),
                media=media
            )
        )

    async def edit(
            self,
            *,
            mountpoint_id: int | str | None = None,
            secret: str | None = None,
            new_description: str | None = None,
            new_metadata: str | None = None,
            new_secret: str | None = None,
            new_pin: str | None = None,
            edited_event: bool | None = None,
            permanent: bool | None = None,
    ):
        return await self.send(
            EditRequest(
                id=self._resolve_mountpoint_id(mountpoint_id),
                secret=secret,
                new_secret=new_secret,
                new_description=new_description,
                new_pin=new_pin,
                permanent=bool(permanent),
                new_metadata=new_metadata,
                edited_event=bool(edited_event),
            )
        )

    async def enable(self, *, secret: str | None = None, mountpoint_id: int | str | None = None):
        return await self.send(
            EnableRequest(
                id=self._resolve_mountpoint_id(mountpoint_id),
                secret=secret,
            )
        )

    async def disable(
            self,
            *,
            mountpoint_id: int | str | None = None,
            secret: str | None = None,
            stop_recording: bool = True,
    ):
        return await self.send(
            DisableRequest(
                id=self._resolve_mountpoint_id(mountpoint_id),
                stop_recording=stop_recording,
                secret=secret,
            )
        )

    async def kick_all(self, *, secret: str | None = None, mountpoint_id: int | str | None = None):
        return await self.send(
            KickAllRequest(
                id=self._resolve_mountpoint_id(mountpoint_id),
                secret=secret,
            )
        )

    # -------------------------
    # Asynchronous viewer API
    # -------------------------
    async def watch(
            self,
            *,
            mountpoint_id: int | str | None = None,
            pin: str | None = None,
            media: List[str] | None = None,
            offer_audio: bool | None = None,
            offer_video: bool | None = None,
            offer_data: bool | None = None,
    ):
        request = WatchRequest(
            id=self._resolve_mountpoint_id(mountpoint_id),
            pin=pin,
            media=media,  # type: ignore
            offer_audio=offer_audio,
            offer_video=offer_video,
            offer_data=offer_data,
        )
        return await self.send(request)

    async def start_streaming(self, jsep: Jsep):
        return await self.send(
            StartRequest(),
            jsep=jsep,
        )

    async def pause(self):
        return await self.send(PauseRequest())

    async def configure(self, streams: List[ConfigureStream]):
        return await self.send(
            ConfigureRequest(
                streams=streams,
            )
        )

    async def switch(self, mountpoint_id: int):
        return await self.send(
            SwitchRequest(
                id=int(mountpoint_id),
            )
        )

    async def stop_streaming(self):
        return await self.send(StopRequest())

    # Convenience aliases
    async def subscribe(self, *args: Any, **kwargs: Any):
        return await self.watch(*args, **kwargs)


__all__ = ["StreamingPlugin"]
