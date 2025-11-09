from typing import Optional, Literal, Dict, Union

from pydantic import BaseModel

from janus_api.models.base import Jsep
from janus_api.models.videoroom import JanusVideoRoomResponse


class JanusError(BaseModel):
    code: int
    reason: str


class JanusBaseResponse(BaseModel):
    janus: str|int  # e.g "success", "error", "ack", "event", etc
    transaction: Optional[str]


# Success Response
class SuccessData(BaseModel):
    id: int  # session ID or handle ID


class SuccessResponse(JanusBaseResponse):
    janus: Literal["success"]
    data: SuccessData


# Error Response
class ErrorResponse(JanusBaseResponse):
    janus: Literal["error"]
    error: JanusError


# Keepalive Response
class KeepAliveResponse(JanusBaseResponse):
    janus: Literal["keepalive"]


# Plugin Event Response

class PluginData(BaseModel):
    plugin: str  # e.g "janus.plugin.videoroom
    data: Union[
        JanusVideoRoomResponse,
    ]


class EventResponse(JanusBaseResponse):
    janus: Literal["event"]
    sender: str|int
    plugindata: PluginData
    jsep: Optional[Jsep]


# WebRTC Based Events

class WebRTCUpResponse(JanusBaseResponse):
    janus: Literal["webrtcup"]
    session_id: str|int
    sender: str|int


class MediaEventResponse(JanusBaseResponse):
    janus: Literal["media"]
    session_id: str|int
    sender: str|int
    type: Literal["audio", "video"]
    receiving: bool


class SlowLinkResponse(JanusBaseResponse):
    janus: Literal["slowlink"]
    session_id: str|int
    sender: str|int
    uplink: bool
    lost: int


class HangupResponse(JanusBaseResponse):
    janus: Literal["hangup"]
    session_id: str|int
    sender: str|int
    reason: Optional[str]


class AckResponse(JanusBaseResponse):
    janus: Literal["ack"]


class TransportPluginInfo(BaseModel):
    name: str
    author: str
    description: str
    version_string: str
    version: int


class PluginInfo(BaseModel):
    name: str
    author: str
    description: str
    version_string: str
    version: int


class InfoResponse(JanusBaseResponse):
    janus: Literal["server_info"]
    name: str
    version_string: str
    version: int
    author: str
    data_channels: str
    ipv6: str
    ice_tcp: str
    transports: Dict[str, TransportPluginInfo]
    plugins: Dict[str, PluginInfo]


WebRTCEvent = Union[WebRTCUpResponse, MediaEventResponse, SlowLinkResponse, HangupResponse, AckResponse]

JanusResponse = Union[
    SuccessResponse,
    ErrorResponse,
    KeepAliveResponse,
    EventResponse,
    # WebRTCUpResponse,
    # MediaEventResponse,
    # SlowLinkResponse,
    # HangupResponse,
    # AckResponse,
    WebRTCEvent,
    InfoResponse,
]

