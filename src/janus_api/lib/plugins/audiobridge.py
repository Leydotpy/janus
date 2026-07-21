from typing import Any

from janus_api.lib.plugins.base import Plugin
from janus_api.models import audiobridge as models


class Audiobridge(Plugin):
    name = "janus.plugin.audiobridge"
    identifier = "audiobridge"

    async def create(self, **kwargs: Any):
        return await self.send(models.AudioBridgeCreateRequest(**kwargs))

    async def edit(self, **kwargs: Any):
        return await self.send(models.AudioBridgeEditRequest(**kwargs))

    async def destroy(self, **kwargs: Any):
        return await self.send(models.AudioBridgeDestroyRequest(**kwargs))

    async def exists(self, *, room: int):
        return await self.send(models.AudioBridgeExistsRequest(room=room))

    async def allowed(self, **kwargs: Any):
        return await self.send(models.AudioBridgeAllowedRequest(**kwargs))

    async def kick(self, *, room: int, id: int, secret: str | None = None):  # noqa: A003
        return await self.send(models.AudioBridgeKickRequest(room=room, id=id, secret=secret))

    async def kick_all(self, *, room: int, secret: str | None = None):
        return await self.send(models.AudioBridgeKickAllRequest(room=room, secret=secret))

    async def list(self):
        return await self.send(models.AudioBridgeListRequest())

    async def listparticipants(self, *, room: int):
        return await self.send(models.AudioBridgeListParticipantsRequest(room=room))

    async def listannouncements(self, *, room: int, secret: str | None = None):
        return await self.send(models.AudioBridgeListAnnouncementsRequest(room=room, secret=secret))

    async def resetdecoder(self, *, room: int, id: int, secret: str | None = None):  # noqa: A003
        return await self.send(models.AudioBridgeResetDecoderRequest(room=room, id=id, secret=secret))

    async def mute(self, *, room: int, id: int, secret: str | None = None):  # noqa: A003
        return await self.send(models.AudioBridgeMuteRequest(room=room, id=id, secret=secret))

    async def unmute(self, *, room: int, id: int, secret: str | None = None):  # noqa: A003
        return await self.send(models.AudioBridgeUnmuteRequest(room=room, id=id, secret=secret))

    async def mute_room(self, *, room: int, secret: str | None = None):
        return await self.send(models.AudioBridgeMuteRoomRequest(room=room, secret=secret))

    async def unmute_room(self, *, room: int, secret: str | None = None):
        return await self.send(models.AudioBridgeUnmuteRoomRequest(room=room, secret=secret))

    async def join(
        self,
        *,
        room: int,
        display: str | None = None,
        pin: str | None = None,
        id: int | None = None,  # noqa: A003
        group: str | None = None,
        rtp: dict[str, Any] | None = None,
        generate_offer: bool | None = None,
    ):
        rtp_info = models.AudioBridgeRtpJoinInfo(**rtp) if rtp is not None else None
        return await self.send(
            models.AudioBridgeJoinRequest(
                room=room,
                display=display,
                pin=pin,
                id=id,
                group=group,
                rtp=rtp_info,
                generate_offer=generate_offer,
            )
        )

    async def leave(self):
        return await self.send(models.AudioBridgeLeaveRequest())

    async def changeroom(
        self,
        *,
        room: int,
        display: str | None = None,
        pin: str | None = None,
        id: int | None = None,  # noqa: A003
        group: str | None = None,
    ):
        return await self.send(
            models.AudioBridgeChangeRoomRequest(
                room=room,
                display=display,
                pin=pin,
                id=id,
                group=group,
            )
        )

    async def play_file(
        self,
        *,
        room: int,
        filename: str,
        secret: str | None = None,
        file_id: str | None = None,
        group: str | None = None,
        loop: bool | None = None,
    ):
        return await self.send(
            models.AudioBridgePlayFileRequest(
                room=room,
                filename=filename,
                secret=secret,
                file_id=file_id,
                group=group,
                loop=loop,
            )
        )

    async def is_playing(self, *, room: int, file_id: str, secret: str | None = None):
        return await self.send(models.AudioBridgeIsPlayingRequest(room=room, file_id=file_id, secret=secret))

    async def stop_file(self, *, room: int, file_id: str, secret: str | None = None):
        return await self.send(models.AudioBridgeStopFileRequest(room=room, file_id=file_id, secret=secret))

    async def stop_all_files(self, *, room: int, secret: str | None = None):
        return await self.send(models.AudioBridgeStopAllFilesRequest(room=room, secret=secret))

    async def rtp_forward(self, **kwargs: Any):
        return await self.send(models.AudioBridgeRtpForwardRequest(**kwargs))

    async def stop_rtp_forward(self, *, room: int, stream_id: int):
        return await self.send(models.AudioBridgeStopRtpForwardRequest(room=room, stream_id=stream_id))

    async def list_forwarders(self, *, room: int, secret: str | None = None):
        return await self.send(models.AudioBridgeListForwardersRequest(room=room))

    async def enable_recording(self, *, room: int, secret: str, mjrs: bool, mjrs_dir: str | None = None):
        return await self.send(
            models.AudioBridgeEnableMjrsRequest(
                room=room,
                secret=secret,
                mjrs=mjrs,
                mjrs_dir=mjrs_dir,
            )
        )


__all__ = ["Audiobridge"]
