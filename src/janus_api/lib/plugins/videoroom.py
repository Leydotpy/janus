"""
VideoRoom plugin implementation adapted to the base Plugin.

This is a cleaned, easier-to-follow implementation of your VideoRoom/Publisher/Subscriber classes.
"""
from typing import List, Literal, Optional, Unpack

from pydantic import ValidationError

from janus_api.models.base import Jsep
from janus_api.models.request import TrickleMessageRequest, TrickleCandidate
from janus_api.models.response import JanusResponse
from janus_api.models.videoroom import (
    VideoRoomCreateRequest,
    ModerateRoomRequest,
    KickUserFromRoomRequest,
    RoomCheckAllowedTokenRequest,
    ListRoomParticipantsRequest,
    RTPForwardRequest,
    RTPForwardStream,
    StopRTPForwardRequest,
    VideoRoomDeleteRequest,
    LeaveRoomRequest,
    VideoRoomExistsRequest,
    ParticipantPublishRequest,
    PublisherConfigureRequest,
    ParticipantUnpublishRequest,
    PublisherJoinAndConfigureRequest,
    ParticipantPublisherJoinRequest,
    ParticipantSubscribeJoinRequest,
    SubscriberStreams,
    ParticipantSubscriberUpdateStreamsRequest,
    ParticipantUnsubscribeRequest,
    ParticipantSubscribeRequest,
    SubscriberStartRequest,
    SubscriberConfigureRequest,
    SubscriberStreamConfigure,
    SubscriberPauseRequest,
)
from janus_api.lib.plugins.base import Plugin, PluginOptions



class VideoRoomMixin(Plugin):

    name = "janus.plugin.videoroom"
    identifier = None

    __slots__ = (
        "__room",
        "__username",
    )

    def __init__(self, *,  room: str | int, username: str,
                 plugin_id: Optional[str] = None, session=None, **kwargs: Unpack[PluginOptions]):
        super().__init__(
            plugin_id=plugin_id,
            session=session,
            **kwargs
        )
        self.__room = str(room)
        self.__username = username

    @property
    def room(self):
        return int(self.__room)

    @property
    def username(self):
        return self.__username

    async def send(self, *args, **kwargs) -> JanusResponse:
        return await super().send(*args, **kwargs)

    async def create(self, **kwargs):
        try:
            kwargs.setdefault("room", self.room)
            body = VideoRoomCreateRequest(request="create", **kwargs)
        except ValidationError as exc:
            raise
        return await self.send(body)

    async def moderate(self, **kwargs):
        body = ModerateRoomRequest(request="moderate", **kwargs)
        return await self.send(body)

    async def kick(self, *, password: str, user_id: str | List[str]):
        if isinstance(user_id, list):
            if not user_id:
                raise ValueError("Empty user list supplied")
            results = []
            for uid in user_id:
                results.append(await self._kick(self.room, password=password, user_id=uid))
            return results
        return await self._kick(self.room, password=password, user_id=user_id)

    async def _kick(self, room, password, user_id):
        body = KickUserFromRoomRequest(request="kick", room=room, id=user_id, secret=password)
        return await self.send(body)

    async def allowed(self, passcode: str, action: Literal["enable", "disable", "add", "remove"], tokens: List[str]):
        body = RoomCheckAllowedTokenRequest(request="allowed", room=self.room, secret=passcode, allowed=tokens,
                                            action=action)
        return await self.send(body)

    async def participants(self):
        body = ListRoomParticipantsRequest(request="listparticipants", room=self.room)
        response = await self.send(body)
        participants = list(response.plugindata.data.participants)
        return [p for p in participants if getattr(p, "publisher", False) is True]

    async def destroy(self, *, secret: str | None = None, permanent: bool = False, room: str | int | None = None):
        body = VideoRoomDeleteRequest(
            request="destroy",
            room=str(room or self.room),
            secret=secret,
            permanent=permanent,
        )
        return await self.send(body)

    async def leave(self):
        body = LeaveRoomRequest(request="leave")
        return await self.send(body)

    async def trickle(self, candidates: List[TrickleCandidate]):
        body = TrickleMessageRequest(janus="trickle", session_id=self.session.id, handle_id=self.id,
                                     candidates=candidates)
        return await self.session.send(body)

    async def complete_trickle(self):
        completed = TrickleMessageRequest(janus="trickle", session_id=self.session.id, handle_id=self.id,
                                          candidate=TrickleCandidate(candidate={"completed": True}))
        return await self.session.send(completed)

    async def exists(self, room: str | int | None = None) -> bool:
        body = VideoRoomExistsRequest(request="exists", room=str(room or self.room))
        response = await self.send(body)
        return bool(response.plugindata.data.exists)


class Publisher(VideoRoomMixin):
    identifier = "publisher"


    async def publish(self, sdp: str, sdp_type: Literal["offer"], **kwargs):
        body = ParticipantPublishRequest(request="publish", **kwargs)
        jsep = Jsep(sdp=sdp, type=sdp_type, trickle=False)
        return await self.send(body, jsep=jsep)

    async def configure(self, sdp: str, sdp_type: Literal["offer"], **kwargs):
        body = PublisherConfigureRequest(request="configure", **kwargs)
        jsep = Jsep(type=sdp_type, sdp=sdp, trickle=False)
        return await self.send(body, jsep=jsep)

    async def unpublish(self):
        body = ParticipantUnpublishRequest(request="unpublish")
        return await self.send(body)

    async def join_and_configure(self, *, sdp: str, sdp_type: Literal["offer"], **kwargs):
        body = PublisherJoinAndConfigureRequest(request="joinandconfigure", display=self.username, room=self.room,
                                                ptype="publisher", **kwargs)
        jsep = Jsep(type=sdp_type, sdp=sdp, trickle=False)
        return await self.send(body, jsep=jsep)

    async def join(self, **kwargs):
        body = ParticipantPublisherJoinRequest(request="join", ptype="publisher", display=self.username, room=self.room,
                                               **kwargs)
        return await self.send(body)

    async def rtp_forward(self, spec) -> JanusResponse:
        if hasattr(spec, "to_payload"):
            payload = spec.to_payload()
        else:
            payload = dict(spec)
        streams = [RTPForwardStream(**stream) for stream in payload.pop("streams", [])]
        body = RTPForwardRequest(**payload, streams=streams)
        return await self.send(body)

    async def stop_rtp_forward(
            self,
            stream_id: int,
            *,
            publisher_id: str | int,
            room: str | int | None = None,
    ) -> JanusResponse:
        body = StopRTPForwardRequest(
            request="stop_rtp_forward",
            room=str(room or self.room),
            publisher_id=str(publisher_id),
            stream_id=stream_id,
        )
        return await self.send(body)


class Subscriber(VideoRoomMixin):
    identifier = "subscriber"

    async def subscribe(self, streams: List[SubscriberStreams]):
        body = ParticipantSubscribeRequest(request="subscribe", streams=streams)
        return await self.send(body)

    async def update(self, add: List[SubscriberStreams] = None, drop: List[SubscriberStreams] = None):
        body = ParticipantSubscriberUpdateStreamsRequest(request="update", subscribe=add, unsubscribe=drop)
        return await self.send(body)

    async def unsubscribe(self, streams: List[SubscriberStreams]):
        body = ParticipantUnsubscribeRequest(request="unsubscribe", streams=streams)
        return await self.send(body)

    async def join(self, *, streams: List[SubscriberStreams]):
        body = ParticipantSubscribeJoinRequest(request="join", ptype="subscriber", use_msid=True, streams=streams,
                                               room=self.room)
        return await self.send(body)

    async def watch(self, *, sdp: str, sdp_type: Literal["answer"]):
        body = SubscriberStartRequest(request="start")
        jsep = Jsep(sdp=sdp, type=sdp_type, trickle=False)
        return await self.send(body, jsep=jsep)

    async def configure(self, streams: List[SubscriberStreamConfigure]):
        body = SubscriberConfigureRequest(request="configure", streams=streams, restart=True)
        return await self.send(body)

    async def resume(self):
        return await self.send(SubscriberStartRequest(request="start"))

    async def pause(self):
        return await self.send(SubscriberPauseRequest(request="pause"))


__all__ = ("Publisher", "Subscriber")
