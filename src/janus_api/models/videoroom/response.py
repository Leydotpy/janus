from typing import Union, Literal, List, Optional, Dict, Any

from pydantic import BaseModel

from janus_api.models.videoroom.fields import Room


class BaseResponse(BaseModel):
    videoroom: str

class CreateResponse(BaseResponse):
    videoroom: Literal["created"]
    room: str
    permanent: bool

class DestroyResponse(BaseResponse):
    room: str


class ErrorResponse(BaseResponse):
    error_code: int
    error: str


class ExistsResponse(BaseResponse):
    room: str
    exists: bool


class AllowedResponse(BaseResponse):
    room: str
    allowed: List[str]


class SuccessResponse(BaseResponse):
    room: Optional[str] = None


class ListResponse(BaseResponse):
    videoroom: Literal["success"]
    list: List[Room]


class Participant(BaseModel):
    id: str
    display: Optional[str]
    metadata: Optional[Dict[str, Any]]
    publisher: bool
    talking: bool


class ParticipantsResponse(BaseResponse):
    videoroom: Literal["participants"]
    room: str
    participants: List[Participant]


class StreamInfo(BaseModel):
    type: Literal["audio", "video", "data"]
    mindex: Optional[int]
    mid: Optional[str]
    disabled: Optional[bool]
    codec: Optional[str]
    description: Optional[str]
    moderated: Optional[bool]
    simulcast: Optional[bool]
    svc: Optional[bool]
    talking: Optional[bool]


class PublisherInfo(BaseModel):
    id: str
    display: Optional[str]
    metadata: Optional[Dict[str, Any]]
    dummy: List[StreamInfo]
    talking: Optional[bool]


class AttendeeInfo(BaseModel):
    id: str
    display: Optional[str]
    metadata: Optional[Dict[str, Any]]


class JoinedResponse(BaseResponse):
    videoroom: Literal["joined"]
    room: str
    description: Optional[str]
    id: str
    private_id: Optional[str]
    publishers: List[PublisherInfo]
    attendees: List[AttendeeInfo]

class EventJoining(BaseModel):
    id: int
    display: Optional[str]
    metadata: Optional[Dict[str, Any]]


class EventPublisherResponse(BaseResponse):
    videoroom: Literal["event"]
    room: str
    publishers: List[PublisherInfo]


class EventJoiningResponse(BaseResponse):
    videoroom: Literal["event"]
    room: str
    joinings: EventJoining


class EventDestroyedResponse(BaseResponse):
    videoroom: Literal["destroyed"]
    room: str


class EventUnpublishedResponse(BaseResponse):
    videoroom: Literal["event"]
    room: Optional[str]
    unpublished: str


class LeavingEvent(BaseResponse):
    leaving: Literal["ok"]


class EventLeavingResponse(BaseResponse):
    videoroom: Literal["event"]
    room: Optional[str]
    leaving: Optional[str]
    display: Optional[str]


class ConfiguredEvent(BaseResponse):
    videoroom: Literal["event"]
    configured: Literal["ok"]


class ForwardingInfo(BaseModel):
    stream_id: Optional[int]
    type: Literal["audio", "video", "data"]
    host: str
    port: int
    local_rtp_port: Optional[int]
    remote_rtp_port: Optional[int]
    ssrc: Optional[int]
    pt: Optional[int]
    substream: Optional[int]
    srtp: Optional[bool]


class RTPForwardResponse(BaseResponse):
    videoroom: Literal["rtp_forward"]
    room: str
    publisher_id: str
    forwarders: List[ForwardingInfo]


class StopRTPForwardResponse(BaseResponse):
    videoroom: Literal["stop_rtp_forward"]
    room: str
    publisher_id: str
    stream_id: int


class ForwarderPublishers(BaseModel):
    publisher_id: str
    forwarders: List[ForwardingInfo]


class ListForwardersResponse(BaseResponse):
    videoroom: Literal["forwarders"]
    room: str
    publishers: List[ForwarderPublishers]


"""Subscribers Response Models"""

class SimulcastInfo(BaseModel):
    enabled: Optional[bool]


class SvcInfo(BaseModel):
    enabled: Optional[bool]


class PlayoutDelayInfo(BaseModel):
    min_delay: Optional[int]
    max_delay: Optional[int]


class SubscriberVideoRoomStream(BaseModel):
    mindex: Optional[int]
    mid: Optional[str]
    type: Literal["video", "audio", "data"]
    active: bool
    feed_id: str
    feed_mid: Optional[str]
    feed_display: Optional[str]
    send: bool
    codec: Optional[str]
    h264_profile: Optional[str] = None
    vp9_profile: Optional[str] = None
    ready: bool
    simulcast: Optional[SimulcastInfo] = None
    svc: Optional[SvcInfo] = None
    playout_delay: Optional[PlayoutDelayInfo] = None
    sources: Optional[int] = None
    source_ids: Optional[List[int]] = None


class SubscriberBaseEvent(BaseModel):
    videoroom: Literal["event", "attached", "updated"]
    room: str


class SubscriberAttachedEvent(SubscriberBaseEvent):
    videoroom: Literal["attached"]
    streams: List[SubscriberVideoRoomStream]


class StartedEvent(SubscriberBaseEvent):
    started: Literal["ok"]


class PausedEvent(SubscriberBaseEvent):
    paused: Literal["ok"]


class LeftEvent(SubscriberBaseEvent):
    left: Literal["ok"]


class SubscriberUpdatedStream(SubscriberVideoRoomStream):
    ...


class UpdatedEvent(SubscriberBaseEvent):
    videoroom: Literal["updated"]
    streams: Optional[List[SubscriberUpdatedStream]]


class SwitchedEvent(SubscriberBaseEvent):
    switched: Literal["ok"]
    changes: int
    streams: Optional[List[SubscriberVideoRoomStream]]


class UpdatingEvent(SubscriberBaseEvent):
    updating: Optional[dict] = {}



JanusVideoRoomResponse = Union[
    CreateResponse,
    DestroyResponse,
    ErrorResponse,
    ExistsResponse,
    ParticipantsResponse,
    AllowedResponse,
    SuccessResponse,
    ListResponse,
    EventDestroyedResponse,
    EventUnpublishedResponse,
    EventLeavingResponse,
    JoinedResponse,
    EventPublisherResponse,
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