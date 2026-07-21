from __future__ import annotations

"""Pydantic models for the Janus VideoCall plugin.

The VideoCall plugin is fully asynchronous according to the Janus
documentation. Requests return plugin events rather than immediate synchronous
success payloads.
"""

from typing import Annotated, Literal, Union

from pydantic import Field

from .common import JanusJsep, PluginErrorResponse, StrictBaseModel


class VideoCallListRequest(StrictBaseModel):
    """List all registered peers.

    Janus replies asynchronously with a `videocall: event` containing
    `result.list`.
    """

    request: Literal["list"] = "list"


class VideoCallRegisterRequest(StrictBaseModel):
    """Register a username to call and be called.

    The docs describe this as a simple first-come-first-served registration
    with no authentication and no explicit unregister operation.
    """

    request: Literal["register"] = "register"
    username: str


class VideoCallCallRequest(StrictBaseModel):
    """Start a call to another registered peer.

    Janus requires this request to be associated with a JSEP offer in the
    outer Janus message.
    """

    request: Literal["call"] = "call"
    username: str


class VideoCallAcceptRequest(StrictBaseModel):
    """Accept an incoming call.

    Janus expects this request to be paired with a JSEP answer completing the
    PeerConnection setup.
    """

    request: Literal["accept"] = "accept"


class VideoCallSetRequest(StrictBaseModel):
    """Update call settings or renegotiate the session.

    Janus documents `set` both for runtime toggles such as audio/video/bitrate
    and for session updates such as adding/removing media or forcing an ICE
    restart when accompanied by new JSEP.
    """

    request: Literal["set"] = "set"
    audio: bool | None = None
    video: bool | None = None
    bitrate: int | None = None
    record: bool | None = None
    filename: str | None = None
    substream: int | None = None
    temporal: int | None = None
    fallback: int | None = None


class VideoCallHangupRequest(StrictBaseModel):
    """Cancel, decline, or terminate a call.

    Janus uses the same request for pre-answer cancellation and for hanging up
    an established call.
    """

    request: Literal["hangup"] = "hangup"


VideoCallRequest = Annotated[
    Union[
        VideoCallListRequest,
        VideoCallRegisterRequest,
        VideoCallCallRequest,
        VideoCallAcceptRequest,
        VideoCallSetRequest,
        VideoCallHangupRequest,
    ],
    Field(discriminator="request"),
]


class VideoCallResultList(StrictBaseModel):
    """`result` payload for `list`."""

    peers: list[str] = Field(alias="list")


class VideoCallRegisteredResult(StrictBaseModel):
    """`result` payload for `register`."""

    event: Literal["registered"]
    username: str


class VideoCallCallingResult(StrictBaseModel):
    """`result` payload notifying the caller that signaling started."""

    event: Literal["calling"]
    username: str


class VideoCallIncomingCallResult(StrictBaseModel):
    """`result` payload notifying the callee of an incoming call."""

    event: Literal["incomingcall"]
    username: str


class VideoCallAcceptedResult(StrictBaseModel):
    """`result` payload notifying both peers that the call was accepted."""

    event: Literal["accepted"]
    username: str


class VideoCallSetResult(StrictBaseModel):
    """`result` payload for a successful `set` request."""

    event: Literal["set"]


class VideoCallUpdateResult(StrictBaseModel):
    """`result` payload notifying the remote side of renegotiation/update."""

    event: Literal["update"]


class VideoCallHangupResult(StrictBaseModel):
    """`result` payload for call teardown notifications."""

    event: Literal["hangup"]
    username: str
    reason: str


VideoCallEventResult = Union[
    VideoCallResultList,
    VideoCallRegisteredResult,
    VideoCallCallingResult,
    VideoCallIncomingCallResult,
    VideoCallAcceptedResult,
    VideoCallSetResult,
    VideoCallUpdateResult,
    VideoCallHangupResult,
]


class VideoCallEventResponse(StrictBaseModel):
    """Asynchronous VideoCall plugin event.

    The actual event kind is carried under `result`, and JSEP may accompany
    call setup or renegotiation related events.
    """

    videocall: Literal["event"]
    result: VideoCallEventResult
    jsep: JanusJsep | None = None


class VideoCallErrorResponse(PluginErrorResponse):
    """Plugin-level VideoCall error response."""

    videocall: Literal["event"]


VideoCallResponse = Union[
    VideoCallEventResponse,
    VideoCallErrorResponse,
]
