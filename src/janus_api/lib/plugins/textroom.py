from typing import Literal, Any

from janus_api.lib.plugins.base import Plugin
from janus_api.models.base import Jsep
from janus_api.models.textroom import TextRoomSetupRequest, TextRoomAckRequest, TextRoomRestartRequest, \
    TextRoomDataListRequest, TextRoomDataCreateRequest, TextRoomDataEditRequest, TextRoomDataDestroyRequest, \
    TextRoomDataExistsRequest, TextRoomJanusListParticipantsRequest, TextRoomDataAllowedRequest, \
    TextRoomDataKickRequest, TextRoomJoinRequest, TextRoomLeaveRequest, TextRoomMessageRequest, \
    TextRoomAnnouncementRequest


class TextRoomPlugin(Plugin):
    name = "janus.plugin.textroom"
    identifier = "textroom"

    async def create(self, *, sdp: str, sdp_type: Literal["offer", "answer"]):
        return await self.send(
            TextRoomSetupRequest(),
            jsep=Jsep(type=sdp_type, sdp=sdp)
        )

    async def ack(self, *, sdp: str, sdp_type: Literal["offer", "answer"]):
        return await self.send(
            TextRoomAckRequest(),
            jsep=Jsep(sdp=sdp, type=sdp_type)
        )

    async def restart(self, *, sdp: str, sdp_type: Literal["offer", "answer"]):
        return await self.send(TextRoomRestartRequest(), jsep=Jsep(sdp=sdp, type=sdp_type))

    async def list_rooms(self, admin_key: str | None = None):
        return await self.send(TextRoomDataListRequest(admin_key=admin_key))

    async def create_room(self, *, room: int | None = None, admin_key: str | None = None,
                          description: str | None = None, secret: str | None = None, pin: str | None = None,
                          is_private: bool | None = None, history: int | None = None, post: str | None = None,
                          permanent: bool | None = None):
        return await self.send(TextRoomDataCreateRequest(
            room=room,
            admin_key=admin_key,
            description=description,
            secret=secret,
            pin=pin,
            is_private=is_private,
            history=history,
            post=post,
            permanent=permanent
        ))

    async def edit_room(self, *, room: int, secret: str, new_description: str | None = None,
                        new_secret: str | None = None, new_pin: str | None = None, new_is_private: bool | None = None,
                        permanent: bool | None = None):
        return await self.send(TextRoomDataEditRequest(
            room=room,
            permanent=permanent,
            new_pin=new_pin,
            new_secret=new_secret,
            new_is_private=new_is_private,
            new_description=new_description,
            secret=secret
        ))

    async def destroy_room(self, *, room: int, secret: str,
                           permanent: bool | None = None):
        return await self.send(TextRoomDataDestroyRequest(
            secret=secret, permanent=permanent, room=room))

    async def exists_room(self, *, room: int):
        return await self.send(TextRoomDataExistsRequest(room=room))

    async def list_participants(self, *, room: int):
        return await self.send(TextRoomJanusListParticipantsRequest(room=room))

    async def allowed(self, *, room: int, action: Literal["enable", "disable", "add", "remove"], secret: str,
                      allowed: list[str] | None = None):
        return await self.send(
            TextRoomDataAllowedRequest(
                room=room,
                action=action,
                secret=secret,
                allowed=allowed
            )
        )

    async def kick(self, *, room: int, username: str, secret: str):
        return await self.send(
            TextRoomDataKickRequest(
                room=room,
                username=username,
                secret=secret
            )
        )

    async def join(self, *, room: int, username: str, pin: str | None = None, display: str | None = None,
                   token: str | None = None, history: bool | None = None):
        return await self.send(
            TextRoomJoinRequest(
                room=room,
                username=username,
                pin=pin,
                display=display,
                token=token,
                history=history,
            )
        )

    async def leave(self, *, room: int):
        return await self.send(
            TextRoomLeaveRequest(
                room=room
            )
        )

    async def message(self, *, room: int, text: str, to: str | None = None, tos: list[str] | None = None,
                      ack: bool = True):
        return await self.send(
            TextRoomMessageRequest(
                room=room,
                text=text,
                ack=ack,
                tos=tos,
                to=to,
            )
        )

    async def announcement(self, *, room: int, text: str, secret: str):
        return await self.send(
            TextRoomAnnouncementRequest(
                room=room,
                text=text,
                secret=secret
            )
        )

    async def send_datachannel_message(self, payload: dict[str, Any]) -> None:
        raise NotImplementedError("Use the aiortc bridge module to establish the TextRoom datachannel.")


__all__ = ["TextRoomPlugin"]
