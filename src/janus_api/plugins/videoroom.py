"""VideoRoom plugin implementation adapted to the base PluginBase.

This is a cleaned, easier-to-follow implementation of your VideoRoom/Publisher/Subscriber classes.
"""
from collections import OrderedDict
from typing import List, Literal, Optional

from pydantic import ValidationError

from janus_api.models.base import Jsep
from janus_api.models.request import TrickleMessageRequest, TrickleCandidate
from janus_api.models.videoroom.request import (
    VideoRoomCreateRequest,
    ModerateRoomRequest,
    KickUserFromRoomRequest,
    RoomCheckAllowedTokenRequest,
    ListRoomParticipantsRequest,
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
from janus_api.plugins.base import PluginBase, PluginRegistry


@PluginRegistry.register(name="videoroom")
class VideoRoomPlugin(PluginBase):
    name = "janus.plugin.videoroom"
    _registry = OrderedDict()

    __slots__ = (
        "__room",
        "__mode",
        "__username"
    )

    def __init_subclass__(cls, mode: Literal["publisher", "subscriber"], **kwargs):
        super().__init_subclass__(**kwargs)
        cls._registry[mode] = cls

    def __new__(cls, mode: Literal["publisher", "subscriber"], *args, **kwargs):
        subclass = cls._registry[mode]
        return object.__new__(subclass)

    def __init__(self, *, plugin_id: Optional[str | int] = None, session=None, room: Optional[str | int] = None,
                 username: Optional[str] = None, mode: Literal["publisher", "subscriber"] = "publisher", **kwargs):
        super().__init__(
            plugin_id=plugin_id,
            session=session,
            username=username,
            mode=mode,
            room=room,
            **kwargs
        )
        if plugin_id is None:
            raise ValueError("plugin_id is required")
        if room is None:
            raise ValueError("room is required")
        self.__room = room
        self.__username = username
        self.__mode = mode

    @property
    def room(self):
        return self.__room

    @property
    def username(self):
        return self.__username

    async def create(self, **kwargs):
        try:
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
        return [p for p in response.data.participants if getattr(p, "publisher", False) is True]

    async def destroy(self, *, secret: str, permanent: bool = False):
        body = VideoRoomDeleteRequest(request="destroy", room=self.room, secret=secret, permanent=permanent)
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

    async def exists(self) -> bool:
        body = VideoRoomExistsRequest(request="exists", room=self.room)
        response = await self.send(body)
        return response.data.exists


class Publisher(VideoRoomPlugin):
    def __init__(self, **kwargs):
        super().__init__(mode="publisher", **kwargs)

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


class Subscriber(VideoRoomPlugin):
    def __init__(self, **kwargs):
        super().__init__(mode="subscriber", **kwargs)

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


VideoRoom = VideoRoomPlugin

__all__ = ("VideoRoom", "Publisher", "Subscriber")
