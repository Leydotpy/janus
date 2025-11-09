import uuid
from typing import Optional, Literal, Union, Dict, List

from pydantic import BaseModel, Field

from janus_api.models.base import Jsep
from janus_api.models.videoroom import VideoRoomRequestBody


class BaseJanusRequest(BaseModel):
    janus: str
    transaction: Optional[str] = Field(default_factory=uuid.uuid4, alias="transaction")


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
    session_id: str
    handle_id: str


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