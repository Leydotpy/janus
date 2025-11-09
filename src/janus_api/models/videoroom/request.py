from typing import Optional, Literal, Dict, List, Union

from pydantic import BaseModel, Field

from janus_api.models.base import PluginMessageBase
from janus_api.models.videoroom.fields import Room, AudioCodec, VideoCodec
from janus_api.utils import generate_id


class VideoRoomCreateRequest(PluginMessageBase, Room):
    request: Literal["create"]


class VideoRoomEditRequest(PluginMessageBase, Room):
    request: Literal["edit"]


class VideoRoomDeleteRequest(PluginMessageBase):
    request: Literal["destroy"]
    room: str
    secret: Optional[str]
    permanent: Optional[bool] = Field(False)


class VideoRoomExistsRequest(PluginMessageBase):
    request: Literal["exists"]
    room: str


class RoomCheckAllowedTokenRequest(PluginMessageBase):
    request: Literal["allowed"]
    secret: Optional[str]
    action: Literal["enable", "disable", "add", "remove"]
    room: str
    allowed: List[str]


class KickUserFromRoomRequest(PluginMessageBase):
    request: Literal["kick"]
    secret: Optional[str]
    room: str
    id: str


class ModerateRoomRequest(PluginMessageBase):
    request: Literal["moderate"]
    secret: Optional[str]
    room: str
    id: str
    mid: str
    mute: bool


class ListRoomRequest(PluginMessageBase):
    request: Literal["list"]


class ListRoomParticipantsRequest(PluginMessageBase):
    request: Literal["listparticipants"]
    room: str


class VideoRoomJoin(PluginMessageBase):
    request: Literal["join"]
    ptype: Literal["publisher", "subscriber"]
    room: str
    pin: Optional[str] = None
    private_id: Optional[str] = None


class ParticipantPublisherJoinRequest(VideoRoomJoin):
    ptype: Literal["publisher"]
    display: Optional[str]
    id: Optional[str] = Field(default_factory=generate_id, alias="id")
    token: Optional[str] = None
    metadata: Optional[Dict[str, str]] = None


class SubscriberStreams(BaseModel):
    feed: str
    mid: str
    crossrefid: str
    sub_mid: Optional[str] = None


class ParticipantSubscribeJoinRequest(VideoRoomJoin):
    ptype: Literal["subscriber"]
    use_msid: Optional[bool] = Field(default=False)
    autoupdate: Optional[bool] = Field(default=True)
    streams: Optional[List[SubscriberStreams]] = None
    feed: Optional[str] = None
    audio: Optional[bool] = None
    video: Optional[bool] = None
    data: Optional[bool] = None
    offer_audio: Optional[bool] = None
    offer_video: Optional[bool] = None
    offer_data: Optional[bool] = None


class StreamDescription(BaseModel):
    mid: str
    description: str


class ParticipantStreamModel(BaseModel):
    mid: str
    keyframe: Optional[bool]
    send: Optional[bool]
    min_delay: Optional[int]
    max_delay: Optional[int]


class ParticipantPublishRequest(PluginMessageBase):
    request: Literal["publish"]
    audiocodec: Optional[AudioCodec] = None
    videocodec: Optional[VideoCodec] = None
    bitrate: Optional[int] = None
    record: Optional[bool] = Field(default=False)
    filename: Optional[str] = Field(default=None)
    display: Optional[str] = None
    metadata: Optional[Dict[str, str]] = None
    audio_level_average: Optional[int] = Field(default=25, ge=0, le=127)
    audio_active_packets: Optional[int] = Field(default=100, gt=0)
    descriptions: Optional[List[StreamDescription]] = None


class ParticipantUnpublishRequest(PluginMessageBase):
    request: Literal["unpublish"]


class PublisherConfigureRequest(ParticipantPublishRequest):
    request: Literal["configure"]
    streams: Optional[List[ParticipantStreamModel]] = None

class PublisherJoinAndConfigureRequest(PublisherConfigureRequest, ParticipantPublisherJoinRequest):
    request: Literal["joinandconfigure"]


class EnableRecordingRequest(PluginMessageBase):
    request: Literal["enable_recording"]
    room: str
    secret: Optional[str]
    record: Optional[bool] = Field(False)


class LeaveRoomRequest(PluginMessageBase):
    request: Literal["leave"]


class SubscriberStartRequest(PluginMessageBase):
    request: Literal["start"]


class ParticipantSubscribeRequest(PluginMessageBase):
    request: Literal["subscribe"]
    streams: List[SubscriberStreams]


class ParticipantUnsubscribeRequest(PluginMessageBase):
    request: Literal["unsubscribe"]
    streams: List[SubscriberStreams]


class ParticipantSubscriberUpdateStreamsRequest(PluginMessageBase):
    request: Literal["update"]
    subscribe: Optional[List[SubscriberStreams]]
    unsubscribe: Optional[List[SubscriberStreams]]


class SubscriberPauseRequest(PluginMessageBase):
    request: Literal["pause"]


class SubscriberSwitchRequest(PluginMessageBase):
    request: Literal["switch"]
    streams: List[SubscriberStreams]


class SubscriberStreamConfigure(BaseModel):
    mid: str
    substream: Optional[int] = None
    temporal: Optional[int] = None
    fallback: Optional[int] = None
    spatial_layer: Optional[int] = None
    temporal_layer: Optional[int] = None
    send: Optional[bool] = False
    min_delay: Optional[int] = None
    max_delay: Optional[int] = None
    audio_level_average: Optional[int] = Field(default=25, ge=0, le=127)
    audio_active_packets: Optional[int] = Field(default=100, gt=0)


class SubscriberConfigureRequest(PluginMessageBase):
    request: Literal["configure"]
    streams: List[SubscriberStreamConfigure]
    restart: Optional[bool] = Field(True)


VideoRoomRequestBody = Union[
    VideoRoomCreateRequest,
    VideoRoomEditRequest,
    VideoRoomDeleteRequest,
    VideoRoomExistsRequest,
    RoomCheckAllowedTokenRequest,
    KickUserFromRoomRequest,
    ModerateRoomRequest,
    ListRoomRequest,
    ListRoomParticipantsRequest,
    ParticipantPublisherJoinRequest,
    ParticipantSubscribeJoinRequest,
    SubscriberStartRequest,
    SubscriberConfigureRequest,
    SubscriberSwitchRequest,
    ParticipantSubscribeRequest,
    ParticipantUnsubscribeRequest,
    ParticipantSubscriberUpdateStreamsRequest,
    SubscriberPauseRequest,
    LeaveRoomRequest,
    EnableRecordingRequest,
    ParticipantUnpublishRequest,
    ParticipantPublishRequest,
    PublisherConfigureRequest,
    PublisherJoinAndConfigureRequest,
]