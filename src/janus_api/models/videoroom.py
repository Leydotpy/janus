from __future__ import annotations

from ..utils import generate_secure_id

"""Pydantic models for the Janus VideoRoom plugin."""

import uuid
from enum import Enum
from typing import Any, Literal, Union, Iterable

from pydantic import Field, model_validator

from .base import PluginMessageBase
from .common import PluginErrorResponse, StrictBaseModel


class AudioCodec(str, Enum):
    opus = "opus"
    g722 = "g722"
    pcmu = "pcmu"
    pcma = "pcma"
    isac32 = "isac32"
    isac16 = "isac16"


class VideoCodec(str, Enum):
    vp8 = "vp8"
    vp9 = "vp9"
    av1 = "av1"
    h264 = "h264"
    h265 = "h265"


class DummyStream(StrictBaseModel):
    codec: VideoCodec = Field(..., description="Video codec to offer, for example vp8 or h264.")
    fmtp: str | None = Field(default=None, description="Optional format parameters for the codec.")


class Room(StrictBaseModel):
    """VideoRoom room configuration shared by create and edit requests."""

    room: int | None = Field(default_factory=generate_secure_id)
    permanent: bool = False
    description: str | None = None
    is_private: bool = False
    secret: str | None = None
    pin: str | None = None
    require_pvtid: bool = False
    signed_tokens: bool = False
    publishers: int = Field(default=10, gt=0)
    bitrate: int = Field(..., gt=0)
    bitrate_cap: bool = False
    fir_freq: int = Field(default=0, ge=0)
    audiocodec: AudioCodec
    videocodec: VideoCodec
    vp9_profile: str | None = None
    h264_profile: str | None = None
    opus_fec: bool = True
    opus_dtx: bool = False
    audiolevel_ext: bool = True
    audiolevel_event: bool = False
    audio_active_packets: int = Field(default=100, gt=0)
    audio_level_average: int = Field(default=25, ge=0, le=127)
    videoorient_ext: bool = True
    playoutdelay_ext: bool = True
    transport_wide_cc_ext: bool = True
    record: bool = False
    rec_dir: str | None = None
    lock_record: bool = False
    notify_joining: bool = False
    require_e2ee: bool = False
    dummy_publisher: bool = False
    dummy_streams: list[DummyStream] | None = None
    threads: int = Field(default=0, ge=0)
    allowed: list[str] | None = None

    @model_validator(mode="after")
    def _validate_room_options(self) -> "Room":
        if self.dummy_streams and not self.dummy_publisher:
            raise ValueError("Dummy streams can only be set when dummy_publisher is enabled.")
        if self.record and not self.rec_dir:
            raise ValueError("rec_dir must be set when recording is enabled.")
        return self

    def prepare_model_for_edit(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class VideoRoomCreateRequest(PluginMessageBase, Room):
    request: Literal["create"] = "create"


class VideoRoomEditRequest(PluginMessageBase, Room):
    request: Literal["edit"] = "edit"


class VideoRoomDeleteRequest(PluginMessageBase):
    request: Literal["destroy"] = "destroy"
    room: int
    secret: str | None = None
    permanent: bool = False


class VideoRoomExistsRequest(PluginMessageBase):
    request: Literal["exists"] = "exists"
    room: int


class RoomCheckAllowedTokenRequest(PluginMessageBase):
    request: Literal["allowed"] = "allowed"
    secret: str | None = None
    action: Literal["enable", "disable", "add", "remove"]
    room: int
    allowed: list[str]


class KickUserFromRoomRequest(PluginMessageBase):
    request: Literal["kick"] = "kick"
    secret: str | None = None
    room: int
    id: int


class ModerateRoomRequest(PluginMessageBase):
    request: Literal["moderate"] = "moderate"
    secret: str | None = None
    room: int
    id: int
    mid: str
    mute: bool


class ListRoomRequest(PluginMessageBase):
    request: Literal["list"] = "list"


class ListRoomParticipantsRequest(PluginMessageBase):
    request: Literal["listparticipants"] = "listparticipants"
    room: int


class RTPForwardStream(StrictBaseModel):
    mid: str
    port: int
    host: str | None = None
    host_family: Literal["ipv4", "ipv6"] | None = None
    ssrc: int | None = None
    pt: int | None = None
    rtcp_port: int | None = None
    simulcast: bool = False
    port_2: int | None = None
    ssrc_2: int | None = None
    pt_2: int | None = None
    port_3: int | None = None
    ssrc_3: int | None = None
    pt_3: int | None = None


class RTPForwardRequest(PluginMessageBase):
    request: Literal["rtp_forward"] = "rtp_forward"
    room: int
    publisher_id: int
    streams: list[RTPForwardStream]
    host: str | None = None
    host_family: Literal["ipv4", "ipv6"] | None = None
    srtp_suite: int | None = None
    srtp_crypto: str | None = None
    admin_key: str | None = None


class StopRTPForwardRequest(PluginMessageBase):
    request: Literal["stop_rtp_forward"] = "stop_rtp_forward"
    room: int
    publisher_id: int
    stream_id: int


class VideoRoomJoin(PluginMessageBase):
    request: Literal["join"] = "join"
    ptype: Literal["publisher", "subscriber"]
    room: int
    pin: str | None = None
    private_id: int | None = None


class ParticipantPublisherJoinRequest(VideoRoomJoin):
    ptype: Literal["publisher"] = "publisher"
    display: str | None = None
    id: int | None = Field(default_factory=generate_secure_id)
    token: str | None = None
    metadata: dict[str, str] | None = None


class SubscriberStreams(StrictBaseModel):
    feed: int
    mid: str
    crossrefid: str
    sub_mid: str | None = None


class ParticipantSubscribeJoinRequest(VideoRoomJoin):
    ptype: Literal["subscriber"] = "subscriber"
    use_msid: bool = False
    autoupdate: bool = True
    streams: list[SubscriberStreams] | None = None
    feed: int | None = None
    audio: bool | None = None
    video: bool | None = None
    data: bool | None = None
    offer_audio: bool | None = None
    offer_video: bool | None = None
    offer_data: bool | None = None


class StreamDescription(StrictBaseModel):
    mid: str
    description: str


class ParticipantStreamModel(StrictBaseModel):
    mid: str
    keyframe: bool | None = None
    send: bool | None = None
    min_delay: int | None = None
    max_delay: int | None = None


class ParticipantPublishRequest(PluginMessageBase):
    request: Literal["publish"] = "publish"
    audiocodec: AudioCodec | None = None
    videocodec: VideoCodec | None = None
    bitrate: int | None = None
    record: bool = False
    filename: str | None = None
    display: str | None = None
    metadata: dict[str, str] | None = None
    audio_level_average: int = Field(default=25, ge=0, le=127)
    audio_active_packets: int = Field(default=100, gt=0)
    descriptions: list[StreamDescription] | None = None


class ParticipantUnpublishRequest(PluginMessageBase):
    request: Literal["unpublish"] = "unpublish"


class PublisherConfigureRequest(ParticipantPublishRequest):
    request: Literal["configure"] = "configure"
    streams: list[ParticipantStreamModel] | None = None


class PublisherJoinAndConfigureRequest(PublisherConfigureRequest, ParticipantPublisherJoinRequest):
    request: Literal["joinandconfigure"] = "joinandconfigure"


class EnableRecordingRequest(PluginMessageBase):
    request: Literal["enable_recording"] = "enable_recording"
    room: int
    secret: str | None = None
    record: bool = False


class LeaveRoomRequest(PluginMessageBase):
    request: Literal["leave"] = "leave"


class SubscriberStartRequest(PluginMessageBase):
    request: Literal["start"] = "start"


class ParticipantSubscribeRequest(PluginMessageBase):
    request: Literal["subscribe"] = "subscribe"
    streams: list[SubscriberStreams]


class ParticipantUnsubscribeRequest(PluginMessageBase):
    request: Literal["unsubscribe"] = "unsubscribe"
    streams: list[SubscriberStreams]


class ParticipantSubscriberUpdateStreamsRequest(PluginMessageBase):
    request: Literal["update"] = "update"
    subscribe: list[SubscriberStreams] | None = None
    unsubscribe: list[SubscriberStreams] | None = None


class SubscriberPauseRequest(PluginMessageBase):
    request: Literal["pause"] = "pause"


class SubscriberSwitchRequest(PluginMessageBase):
    request: Literal["switch"] = "switch"
    streams: list[SubscriberStreams]


class SubscriberStreamConfigure(StrictBaseModel):
    mid: str
    substream: int | None = None
    temporal: int | None = None
    fallback: int | None = None
    spatial_layer: int | None = None
    temporal_layer: int | None = None
    send: bool = False
    min_delay: int | None = None
    max_delay: int | None = None
    audio_level_average: int = Field(default=25, ge=0, le=127)
    audio_active_packets: int = Field(default=100, gt=0)


class SubscriberConfigureRequest(PluginMessageBase):
    request: Literal["configure"] = "configure"
    streams: list[SubscriberStreamConfigure]
    restart: bool = True


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
    RTPForwardRequest,
    StopRTPForwardRequest,
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


class CreateResponse(StrictBaseModel):
    videoroom: Literal["created"] = "created"
    room: int | str
    permanent: bool


class DestroyedResponse(StrictBaseModel):
    videoroom: Literal["destroyed"] = "destroyed"
    room: int | str


DestroyResponse = DestroyedResponse
EventDestroyedResponse = DestroyedResponse


class VideoRoomErrorResponse(PluginErrorResponse):
    videoroom: str


class ExistsResponse(StrictBaseModel):
    videoroom: Literal["success"] = "success"
    room: int | str
    exists: bool


class AllowedResponse(StrictBaseModel):
    videoroom: Literal["success"] = "success"
    room: int | str
    allowed: list[str]


class SuccessResponse(StrictBaseModel):
    videoroom: Literal["success"] = "success"
    room: int | str | None = None
    permanent: bool | None = None


class ListResponse(StrictBaseModel):
    videoroom: Literal["success"] = "success"
    rooms: list[Room] = Field(alias="list")


class Participant(StrictBaseModel):
    id: int | str
    display: str | None = None
    metadata: dict[str, Any] | None = None
    publisher: bool
    talking: bool


class ParticipantsResponse(StrictBaseModel):
    videoroom: Literal["participants"] = "participants"
    room: int | str
    participants: Iterable[Participant] = Field(default_factory=list)


class StreamInfo(StrictBaseModel):
    type: Literal["audio", "video", "data"]
    mindex: int | None = None
    mid: str | None = None
    disabled: bool | None = None
    codec: str | None = None
    description: str | None = None
    moderated: bool | None = None
    simulcast: bool | None = None
    svc: bool | None = None
    talking: bool | None = None


class PublisherInfo(StrictBaseModel):
    id: int | str
    display: str | None = None
    metadata: dict[str, Any] | None = None
    streams: list[StreamInfo] = Field(default_factory=list)
    dummy: bool | None = None
    talking: bool | None = None


class AttendeeInfo(StrictBaseModel):
    id: int | str
    display: str | None = None
    metadata: dict[str, Any] | None = None


class JoinedResponse(StrictBaseModel):
    videoroom: Literal["joined"] = "joined"
    room: int | str
    description: str | None = None
    id: int | str
    private_id: int | str | None = None
    publishers: list[PublisherInfo] = Field(default_factory=list)
    attendees: list[AttendeeInfo] = Field(default_factory=list)


class EventJoining(StrictBaseModel):
    id: int | str
    display: str | None = None
    metadata: dict[str, Any] | None = None


class EventPublisherResponse(StrictBaseModel):
    videoroom: Literal["event"] = "event"
    room: int | str
    publishers: list[PublisherInfo]


class EventJoiningResponse(StrictBaseModel):
    videoroom: Literal["event"] = "event"
    room: int | str
    joinings: EventJoining


class EventUnpublishedResponse(StrictBaseModel):
    videoroom: Literal["event"] = "event"
    room: int | str | None = None
    unpublished: int | str


class EventLeavingResponse(StrictBaseModel):
    videoroom: Literal["event"] = "event"
    room: int | str | None = None
    leaving: int | str | None = None
    display: str | None = None


class ConfiguredEvent(StrictBaseModel):
    videoroom: Literal["event"] = "event"
    configured: Literal["ok"] = "ok"


class ForwardingInfo(StrictBaseModel):
    stream_id: int | None = None
    type: Literal["audio", "video", "data"]
    host: str
    port: int
    local_rtp_port: int | None = None
    remote_rtp_port: int | None = None
    ssrc: int | None = None
    pt: int | None = None
    substream: int | None = None
    srtp: bool | None = None


class RTPForwardResponse(StrictBaseModel):
    videoroom: Literal["rtp_forward"] = "rtp_forward"
    room: int | str
    publisher_id: int | str
    forwarders: list[ForwardingInfo]


class StopRTPForwardResponse(StrictBaseModel):
    videoroom: Literal["stop_rtp_forward"] = "stop_rtp_forward"
    room: int | str
    publisher_id: int | str
    stream_id: int


class ForwarderPublishers(StrictBaseModel):
    publisher_id: int | str
    forwarders: list[ForwardingInfo]


class ListForwardersResponse(StrictBaseModel):
    videoroom: Literal["forwarders"] = "forwarders"
    room: int | str
    publishers: list[ForwarderPublishers]


class SimulcastInfo(StrictBaseModel):
    enabled: bool | None = None


class SvcInfo(StrictBaseModel):
    enabled: bool | None = None


class PlayoutDelayInfo(StrictBaseModel):
    min_delay: int | None = None
    max_delay: int | None = None


class SubscriberVideoRoomStream(StrictBaseModel):
    mindex: int | None = None
    mid: str | None = None
    type: Literal["video", "audio", "data"]
    active: bool
    feed_id: int | str
    feed_mid: str | None = None
    feed_display: str | None = None
    send: bool
    codec: str | None = None
    h264_profile: str | None = None
    vp9_profile: str | None = None
    ready: bool
    simulcast: SimulcastInfo | None = None
    svc: SvcInfo | None = None
    playout_delay: PlayoutDelayInfo | None = None
    sources: int | None = None
    source_ids: list[int] | None = None


class SubscriberAttachedEvent(StrictBaseModel):
    videoroom: Literal["attached"] = "attached"
    room: int | str
    streams: list[SubscriberVideoRoomStream]


class StartedEvent(StrictBaseModel):
    videoroom: Literal["event"] = "event"
    room: int | str
    started: Literal["ok"] = "ok"


class PausedEvent(StrictBaseModel):
    videoroom: Literal["event"] = "event"
    room: int | str
    paused: Literal["ok"] = "ok"


class LeftEvent(StrictBaseModel):
    videoroom: Literal["event"] = "event"
    room: int | str
    left: Literal["ok"] = "ok"


class UpdatedEvent(StrictBaseModel):
    videoroom: Literal["updated"] = "updated"
    room: int | str
    streams: list[SubscriberVideoRoomStream] | None = None


class SwitchedEvent(StrictBaseModel):
    videoroom: Literal["event"] = "event"
    room: int | str
    switched: Literal["ok"] = "ok"
    changes: int
    streams: list[SubscriberVideoRoomStream] | None = None


class UpdatingEvent(StrictBaseModel):
    videoroom: Literal["event"] = "event"
    room: int | str
    updating: dict[str, Any] = Field(default_factory=dict)


JanusVideoRoomResponse = Union[
    CreateResponse,
    DestroyedResponse,
    VideoRoomErrorResponse,
    ExistsResponse,
    AllowedResponse,
    ListResponse,
    ParticipantsResponse,
    SuccessResponse,
    JoinedResponse,
    EventPublisherResponse,
    EventJoiningResponse,
    EventUnpublishedResponse,
    EventLeavingResponse,
    ConfiguredEvent,
    RTPForwardResponse,
    StopRTPForwardResponse,
    ListForwardersResponse,
    SubscriberAttachedEvent,
    StartedEvent,
    PausedEvent,
    LeftEvent,
    UpdatedEvent,
    SwitchedEvent,
    UpdatingEvent,
]


__all__ = (
    "AllowedResponse",
    "AttendeeInfo",
    "AudioCodec",
    "ConfiguredEvent",
    "CreateResponse",
    "DummyStream",
    "EventDestroyedResponse",
    "EventJoining",
    "EventJoiningResponse",
    "EventLeavingResponse",
    "EventPublisherResponse",
    "EventUnpublishedResponse",
    "ExistsResponse",
    "ForwarderPublishers",
    "ForwardingInfo",
    "JanusVideoRoomResponse",
    "JoinedResponse",
    "KickUserFromRoomRequest",
    "LeftEvent",
    "ListForwardersResponse",
    "ListResponse",
    "ListRoomParticipantsRequest",
    "ListRoomRequest",
    "ModerateRoomRequest",
    "Participant",
    "ParticipantPublishRequest",
    "ParticipantPublisherJoinRequest",
    "ParticipantStreamModel",
    "ParticipantSubscribeJoinRequest",
    "ParticipantSubscribeRequest",
    "ParticipantSubscriberUpdateStreamsRequest",
    "ParticipantUnpublishRequest",
    "ParticipantUnsubscribeRequest",
    "ParticipantsResponse",
    "PausedEvent",
    "PlayoutDelayInfo",
    "PublisherConfigureRequest",
    "PublisherInfo",
    "PublisherJoinAndConfigureRequest",
    "RTPForwardRequest",
    "RTPForwardResponse",
    "RTPForwardStream",
    "Room",
    "RoomCheckAllowedTokenRequest",
    "SimulcastInfo",
    "StartedEvent",
    "StopRTPForwardRequest",
    "StopRTPForwardResponse",
    "StreamDescription",
    "StreamInfo",
    "SubscriberAttachedEvent",
    "SubscriberConfigureRequest",
    "SubscriberPauseRequest",
    "SubscriberStartRequest",
    "SubscriberStreamConfigure",
    "SubscriberStreams",
    "SubscriberSwitchRequest",
    "SubscriberVideoRoomStream",
    "SuccessResponse",
    "SvcInfo",
    "SwitchedEvent",
    "UpdatedEvent",
    "UpdatingEvent",
    "VideoCodec",
    "VideoRoomCreateRequest",
    "VideoRoomDeleteRequest",
    "VideoRoomEditRequest",
    "VideoRoomErrorResponse",
    "VideoRoomExistsRequest",
    "VideoRoomJoin",
    "VideoRoomRequestBody",
)
