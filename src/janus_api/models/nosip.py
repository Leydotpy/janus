from __future__ import annotations

"""Pydantic models for the Janus NoSIP plugin.

NoSIP is documented as an RTP bridge where the application owns signaling and
Janus converts between WebRTC JSEP and legacy/plain SDP.
"""

from typing import Annotated, Literal, Union

from pydantic import Field

from .common import JanusJsep, PluginErrorResponse, StrictBaseModel


class NoSipGenerateRequest(StrictBaseModel):
    """Convert a WebRTC JSEP offer/answer into a plain SDP description.

    Janus documents this as asynchronous. The request carries its WebRTC JSEP
    externally in the Janus envelope, while this plugin body specifies NoSIP
    options such as SRTP policy.
    """

    request: Literal["generate"] = "generate"
    info: str | None = None
    srtp: Literal["sdes_mandatory", "sdes_optional"] | None = None
    srtp_profile: str | None = None


class NoSipProcessRequest(StrictBaseModel):
    """Convert a legacy/plain SDP offer or answer into JSEP.

    Janus replies asynchronously with `processed` and a generated JSEP offer
    or answer in the outer event.
    """

    request: Literal["process"] = "process"
    type: Literal["offer", "answer"]
    sdp: str
    info: str | None = None
    srtp: Literal["sdes_mandatory", "sdes_optional"] | None = None
    srtp_profile: str | None = None


class NoSipHangupRequest(StrictBaseModel):
    """Terminate the current bridged media session.

    Janus documents this as asynchronous and sends an `hangingup` event.
    """

    request: Literal["hangup"] = "hangup"


class NoSipRecordingRequest(StrictBaseModel):
    """Start or stop per-direction call recording.

    The docs explain that local and peer audio/video can be recorded
    separately, all sharing the same filename prefix.
    """

    request: Literal["recording"] = "recording"
    action: Literal["start", "stop"]
    audio: bool | None = None
    video: bool | None = None
    peer_audio: bool | None = None
    peer_video: bool | None = None
    filename: str | None = None


class NoSipKeyframeRequest(StrictBaseModel):
    """Request a video keyframe from the WebRTC user, the peer, or both."""

    request: Literal["keyframe"] = "keyframe"
    user: bool | None = None
    peer: bool | None = None


class NoSipForwardStreamRequest(StrictBaseModel):
    """One stream entry within a NoSIP RTP forward request."""

    type: Literal["audio", "video", "peer_audio", "peer_video"]
    host: str
    host_family: Literal["ipv4", "ipv6"] | None = None
    port: int
    ssrc: int | None = None
    pt: int | None = None
    srtp_suite: Literal[32, 80] | None = None
    srtp_crypto: str | None = None


class NoSipRtpForwardRequest(StrictBaseModel):
    """Create one or more RTP forwarders for the active call."""

    request: Literal["rtp_forward"] = "rtp_forward"
    streams: list[NoSipForwardStreamRequest]


class NoSipStopRtpForwardRequest(StrictBaseModel):
    """Stop one previously created RTP forwarder."""

    request: Literal["stop_rtp_forward"] = "stop_rtp_forward"
    stream_id: int


class NoSipListForwardersRequest(StrictBaseModel):
    """List all RTP forwarders for the active call."""

    request: Literal["listforwarders"] = "listforwarders"


NoSipRequest = Annotated[
    Union[
        NoSipGenerateRequest,
        NoSipProcessRequest,
        NoSipHangupRequest,
        NoSipRecordingRequest,
        NoSipKeyframeRequest,
        NoSipRtpForwardRequest,
        NoSipStopRtpForwardRequest,
        NoSipListForwardersRequest,
    ],
    Field(discriminator="request"),
]


class NoSipGeneratedResult(StrictBaseModel):
    """`result` payload for `generate`."""

    event: Literal["generated"]
    type: Literal["offer", "answer"]
    sdp: str
    unique_id: str


class NoSipProcessedResult(StrictBaseModel):
    """`result` payload for `process`.

    Janus may also attach the corresponding JSEP offer/answer to the outer
    event.
    """

    event: Literal["processed"]
    srtp: Literal["sdes_mandatory", "sdes_optional"] | None = None
    unique_id: str


class NoSipSimpleStatusResult(StrictBaseModel):
    """Simple status event with only an event name."""

    event: Literal["hangingup", "recordingupdated", "keyframesent"]


class NoSipForwarder(StrictBaseModel):
    """RTP forwarder description returned by NoSIP."""

    stream_id: int
    type: Literal["audio", "video", "peer_audio", "peer_video"]
    host: str
    port: int
    media: Literal["audio", "video"]
    ssrc: int | None = None
    pt: int | None = None
    srtp: bool | None = None


class NoSipRtpForwardResult(StrictBaseModel):
    """`result` payload for `rtp_forward`."""

    event: Literal["rtp_forward"]
    forwarders: list[NoSipForwarder]


class NoSipStopRtpForwardResult(StrictBaseModel):
    """`result` payload for `stop_rtp_forward`."""

    event: Literal["stop_rtp_forward"]
    stream_id: int


class NoSipForwardersResult(StrictBaseModel):
    """`result` payload for `listforwarders`."""

    event: Literal["forwarders"]
    forwarders: list[NoSipForwarder]


NoSipEventResult = Union[
    NoSipGeneratedResult,
    NoSipProcessedResult,
    NoSipSimpleStatusResult,
    NoSipRtpForwardResult,
    NoSipStopRtpForwardResult,
    NoSipForwardersResult,
]


class NoSipEventResponse(StrictBaseModel):
    """Asynchronous NoSIP plugin event response."""

    nosip: Literal["event"]
    result: NoSipEventResult
    jsep: JanusJsep | None = None


class NoSipErrorResponse(PluginErrorResponse):
    """Plugin-level NoSIP error response."""

    nosip: Literal["event"]


NoSipResponse = Union[
    NoSipEventResponse,
    NoSipErrorResponse,
]
