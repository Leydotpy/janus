from __future__ import annotations

from typing import Optional, Literal, Dict, Union, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from janus_api.models.audiobridge import AudioBridgeResponse
from janus_api.models.base import Jsep
from janus_api.models.echotest import EchoTestResponse
from janus_api.models.nosip import NoSipResponse
from janus_api.models.sip import SipResponse
from janus_api.models.streaming import StreamingResponse
from janus_api.models.textroom import TextRoomResponse
from janus_api.models.videocall import VideoCallResponse
from janus_api.models.videoroom import JanusVideoRoomResponse


class JanusError(BaseModel):
    code: int
    reason: str


class JanusBaseResponse(BaseModel):
    janus: Union[str, int]
    transaction: Optional[Union[str, UUID]] = None
    session_id: Optional[Union[str, int]] = None

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    # Internal discriminator used only for validation.
    kind: str = Field(default="", exclude=True)


class SuccessData(BaseModel):
    id: Union[str, int]


class SuccessResponse(JanusBaseResponse):
    janus: Literal["success"]
    data: SuccessData


class ErrorResponse(JanusBaseResponse):
    janus: Literal["error"]
    error: JanusError


class KeepAliveResponse(JanusBaseResponse):
    janus: Literal["keepalive"]


class PluginData(BaseModel):
    plugin: str
    data: Union[
        JanusVideoRoomResponse,
        AudioBridgeResponse,
        EchoTestResponse,
        NoSipResponse,
        SipResponse,
        StreamingResponse,
        TextRoomResponse,
        VideoCallResponse,
        Dict[str, Any],
    ]


class EventResponse(JanusBaseResponse):
    janus: Literal["event"]
    sender: Union[str, int]
    plugindata: PluginData
    jsep: Optional[Jsep] = None


# WebRTC Events
class WebRTCUpResponse(JanusBaseResponse):
    janus: Literal["webrtcup"]
    sender: Union[str, int]


class MediaEventResponse(JanusBaseResponse):
    janus: Literal["media"]
    sender: Union[str, int]
    type: Literal["audio", "video"]
    receiving: bool


class SlowLinkResponse(JanusBaseResponse):
    janus: Literal["slowlink"]
    sender: Union[str, int]
    uplink: bool
    lost: int


class HangupResponse(JanusBaseResponse):
    janus: Literal["hangup"]
    sender: Union[str, int]
    reason: Optional[str] = None


class TimeoutResponse(JanusBaseResponse):
    janus: Literal["timeout"]


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
    data_channels: bool
    ipv6: bool
    ice_tcp: bool
    transports: Dict[str, TransportPluginInfo]
    plugins: Dict[str, PluginInfo]


WebRTCEvent = Union[WebRTCUpResponse, MediaEventResponse, SlowLinkResponse, HangupResponse, AckResponse]

# Master Union
JanusResponse = Union[
    SuccessResponse,
    ErrorResponse,
    KeepAliveResponse,
    EventResponse,
    WebRTCEvent,
    TimeoutResponse,
    InfoResponse,
    JanusBaseResponse  # Fallback for unknown events
]
