from __future__ import annotations

"""Pydantic models for the Janus EchoTest plugin.

The EchoTest plugin documents a single unnamed asynchronous request whose body
may carry any subset of the supported media-control fields.
"""

from typing import Union, Literal

from .common import JanusJsep, PluginErrorResponse, StrictBaseModel


class EchoTestRequest(StrictBaseModel):
    """Unnamed EchoTest request.

    Janus documents that all fields are optional. The same request body can be
    used both during initial PeerConnection negotiation and later to update
    runtime behaviour such as echoing audio/video, bitrate caps, recording,
    or simulcast/SVC layer selection.
    """

    audio: bool | None = None
    audiocodec: str | None = None
    video: bool | None = None
    videocodec: str | None = None
    videoprofile: str | None = None
    bitrate: int | None = None
    record: bool | None = None
    filename: str | None = None
    substream: int | None = None
    temporal: int | None = None
    svc: bool | None = None
    spatial_layer: int | None = None
    temporal_layer: int | None = None


class EchoTestOkResponse(StrictBaseModel):
    """Successful EchoTest response.

    The docs show `echotest: event` with `result: ok`. A JSEP answer may be
    attached externally when the request negotiated or renegotiated a session.
    """

    echotest: Literal["event"]
    result: Literal["ok"]
    jsep: JanusJsep | None = None


class EchoTestDoneResponse(StrictBaseModel):
    """Session-ended notification.

    Janus emits `result: done` if it detects loss of the associated
    PeerConnection.
    """

    echotest: Literal["event"]
    result: Literal["done"]


class EchoTestErrorResponse(PluginErrorResponse):
    """Plugin-level EchoTest error response."""

    echotest: Literal["event"]


EchoTestResponse = Union[
    EchoTestOkResponse,
    EchoTestDoneResponse,
    EchoTestErrorResponse,
]
