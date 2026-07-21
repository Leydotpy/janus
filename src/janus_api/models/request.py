import uuid
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, ConfigDict

from janus_api.models.audiobridge import AudioBridgeRequest
from janus_api.models.base import Jsep
from janus_api.models.echotest import EchoTestRequest
from janus_api.models.nosip import NoSipRequest
from janus_api.models.sip import SipRequest
from janus_api.models.streaming import StreamingRequest
from janus_api.models.textroom import TextRoomRequest
from janus_api.models.videocall import VideoCallRequest
from janus_api.models.videoroom import VideoRoomRequestBody


class BaseJanusRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )
    janus: str
    transaction: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), alias="transaction")


class CreateSessionRequest(BaseJanusRequest):
    janus: Literal["create"]


class KeepAliveRequest(BaseJanusRequest):
    janus: Literal["keepalive"]
    session_id: int|str


class DestroySessionRequest(BaseJanusRequest):
    janus: Literal["destroy"]
    session_id: int|str


class AttachPluginRequest(BaseJanusRequest):
    janus: Literal["attach"]
    session_id: str|int
    plugin: str|int # e.g., "janus.plugin.videoroom"


class DetachPluginRequest(BaseJanusRequest):
    janus: Literal["detach"]
    session_id: str|int
    handle_id: str|int


PluginRequestBody = Union[
    AudioBridgeRequest,
    EchoTestRequest,
    NoSipRequest,
    SipRequest,
    StreamingRequest,
    TextRoomRequest,
    VideoCallRequest,
    VideoRoomRequestBody,
]

class PluginMessageRequest(BaseJanusRequest):
    janus: Literal["message"]
    session_id: str|int
    handle_id: str|int
    body: PluginRequestBody
    jsep: Optional[Jsep] = None


class TrickleCandidate(BaseModel):
    sdpMid: Optional[str] = None
    sdpMLineIndex: Optional[int] = None
    candidate: Union[str, Dict[str, bool]]  # could be "completed": true


class TrickleRequest(BaseJanusRequest):
    janus: Literal["trickle"]
    candidate: Optional[TrickleCandidate] = None
    candidates: Optional[List[TrickleCandidate]] = None


class TrickleMessageRequest(TrickleRequest):
    session_id: str | int
    handle_id: str | int


class HangupRequest(BaseJanusRequest):
    janus: Literal["hangup"]
    session_id: str
    handle_id: str


class PluginJespMessageRequest(PluginMessageRequest):
    jsep: Jsep


class InfoRequest(BaseJanusRequest):
    janus: Literal["info"]


JanusRequest = Union[
    CreateSessionRequest,
    KeepAliveRequest,
    AttachPluginRequest,
    DetachPluginRequest,
    PluginMessageRequest,
    TrickleMessageRequest,
    HangupRequest,
    PluginJespMessageRequest,
    InfoRequest,
    DestroySessionRequest,
]
