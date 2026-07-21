from __future__ import annotations

"""Pydantic models for the Janus Streaming plugin."""

from typing import Annotated, Literal, TypedDict, Union

from pydantic import Field

from .common import JanusJsep, StrictBaseModel

MediaKind = Literal["audio", "video", "data"]
MountpointType = Literal["rtp", "live", "ondemand", "rtsp"]
TrackType = Literal["audio", "video", "data"]


class Track(TypedDict):
    """Base per-track structure used by multistream mountpoints."""

    mid: str
    type: MediaKind
    label: str | None
    msid: str | None
    mindex: int | None
    age_ms: int | None


class AudioTrack(Track):
    type: Literal["audio"]
    port: int | None
    rtp_port: int | None
    multicast: str | None
    bind_interface: str | None
    pt: int | None
    rtpmap: str | None
    fmtp: str | None
    mcast: str | None
    iface: str | None
    codec: str | None
    skew: bool


class VideoTrack(Track):
    type: Literal["video"]
    port: int | None
    rtp_port: int | None
    multicast: str | None
    bind_interface: str | None
    pt: int | None
    codec: str | None
    fmtp: str | None
    simulcast: bool
    port2: int | None
    port3: int | None
    skew: bool
    svc: bool
    h264_sps: str | None
    rtpmap: str | None
    mcast: str | None
    iface: str | None


class DataTrack(Track):
    type: Literal["data"]
    port: int | None
    multicast: str | None
    bind_interface: str | None
    data_type: Literal["text", "binary"]
    buffer_latest_message: bool


MediaStream = Union[AudioTrack, VideoTrack, DataTrack]


class MountPoint(TypedDict, total=False):
    type: MountpointType
    id: int
    description: str | None
    metadata: str | None
    is_private: bool
    secret: str | None
    pin: str | None
    enabled: bool | None
    permanent: bool
    threads: int
    collision_ms: int | None
    playoutdelay_ext: bool
    abscapturetime_src_ext_id: int | None
    srtpsuite: Literal[32, 80] | None
    srtpcrypto: str | None
    e2ee: bool
    bufferkf_ms: int
    bufferkf_bytes: int
    media: list[MediaStream]
    url: str | None
    rtsp_user: str | None
    rtsp_pwd: str | None
    rtsp_quirk: bool
    rtsp_failcheck: bool
    rtspiface: str | None
    rtsp_reconnect_delay: int | None
    rtsp_session_timeout: int | None
    rtsp_timeout: int | None
    rtsp_conn_timeout: int | None
    rtsp_notify_changes: bool


class CreateMediaBase(StrictBaseModel):
    type: TrackType
    mid: str
    msid: str | None = None
    label: str | None = None


class CreateAudioMedia(CreateMediaBase):
    type: Literal["audio"] = "audio"
    mcast: str | None = None
    iface: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    rtcpport: int | None = Field(default=None, ge=1, le=65535)
    pt: int | None = Field(default=None, ge=0, le=127)
    codec: str | None = None
    fmtp: str | None = None
    skew: bool = False


class CreateVideoMedia(CreateMediaBase):
    type: Literal["video"] = "video"
    mcast: str | None = None
    iface: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    rtcpport: int | None = Field(default=None, ge=1, le=65535)
    pt: int | None = Field(default=None, ge=0, le=127)
    codec: str | None = None
    fmtp: str | None = None
    skew: bool = False
    simulcast: bool = False
    port2: int | None = Field(default=None, ge=1, le=65535)
    port3: int | None = Field(default=None, ge=1, le=65535)
    svc: bool = False
    h264sps: str | None = None
    collision: int | None = Field(default=None, ge=0)


class CreateDataMedia(CreateMediaBase):
    type: Literal["data"] = "data"
    mcast: str | None = None
    iface: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    datatype: Literal["text", "binary"] = "text"
    databuffermsg: bool = False


CreateMedia = Annotated[
    Union[CreateAudioMedia, CreateVideoMedia, CreateDataMedia],
    Field(discriminator="type"),
]


class RecordingMedia(StrictBaseModel):
    mid: str
    filename: str | None = None


class ConfigureStream(StrictBaseModel):
    mid: str
    send: bool | None = None
    substream: int | None = Field(default=None, ge=0, le=2)
    temporal: int | None = Field(default=None, ge=0, le=2)
    fallback: int | None = Field(default=250_000, ge=0, description="Microseconds")
    spatial_layer: int | None = Field(default=None, ge=0, le=1)
    temporal_layer: int | None = Field(default=None, ge=0, le=2)
    min_delay: int | None = Field(default=None, ge=0)
    max_delay: int | None = Field(default=None, ge=0)


class ListRequest(StrictBaseModel):
    request: Literal["list"] = "list"


class InfoRequest(StrictBaseModel):
    request: Literal["info"] = "info"
    id: int
    secret: str | None = None


class CreateRequest(StrictBaseModel):
    request: Literal["create"] = "create"
    admin_key: str | None = None
    type: MountpointType
    id: int | None = Field(default=None, ge=0)
    name: str | None = None
    description: str | None = None
    metadata: str | None = None
    secret: str | None = None
    pin: str | None = None
    is_private: bool = True
    permanent: bool = False
    enabled: bool = False
    media: list[CreateMedia] = Field(default_factory=list)
    filename: str | None = None
    audio: bool | None = None
    video: bool | None = None
    data: bool | None = None
    audioport: int | None = Field(default=None, ge=1, le=65535)
    audiortcpport: int | None = Field(default=None, ge=1, le=65535)
    audiomcast: str | None = None
    audioiface: str | None = None
    audiopt: int | None = Field(default=None, ge=0, le=127)
    audiocodec: str | None = None
    audiofmtp: str | None = None
    audioskew: bool | None = None
    videoport: int | None = Field(default=None, ge=1, le=65535)
    videortcpport: int | None = Field(default=None, ge=1, le=65535)
    videomcast: str | None = None
    videoiface: str | None = None
    videopt: int | None = Field(default=None, ge=0, le=127)
    videocodec: str | None = None
    videofmtp: str | None = None
    videosimulcast: bool | None = None
    videoport2: int | None = Field(default=None, ge=1, le=65535)
    videoport3: int | None = Field(default=None, ge=1, le=65535)
    videoskew: bool | None = None
    videosvc: bool | None = None
    h264sps: str | None = None
    collision: int | None = Field(default=None, ge=0)
    dataport: int | None = Field(default=None, ge=1, le=65535)
    datamcast: str | None = None
    dataiface: str | None = None
    datatype: Literal["text", "binary"] | None = None
    databuffermsg: bool | None = None
    threads: int | None = Field(default=None, ge=0)
    bufferkf_ms: int | None = Field(default=None, ge=0)
    bufferkf_bytes: int | None = Field(default=None, ge=0)
    srtpsuite: Literal[32, 80] | None = None
    srtpcrypto: str | None = None
    e2ee: bool | None = None
    playoutdelay_ext: bool | None = None
    abscapturetime_src_ext_id: int | None = Field(default=None, ge=1, le=14)
    url: str | None = None
    rtsp_user: str | None = None
    rtsp_pwd: str | None = None
    rtsp_quirk: bool | None = None
    rtsp_failcheck: bool | None = None
    rtspiface: str | None = None
    rtsp_reconnect_delay: int | None = Field(default=None, ge=0)
    rtsp_session_timeout: int | None = Field(default=None, ge=0)
    rtsp_timeout: int | None = Field(default=None, ge=0)
    rtsp_conn_timeout: int | None = Field(default=None, ge=0)
    rtsp_notify_changes: bool | None = None


class DestroyRequest(StrictBaseModel):
    request: Literal["destroy"] = "destroy"
    id: int
    secret: str | None = None
    permanent: bool = False


class EditRequest(StrictBaseModel):
    request: Literal["edit"] = "edit"
    id: int
    secret: str | None = None
    new_description: str | None = None
    new_metadata: str | None = None
    new_secret: str | None = None
    new_pin: str | None = None
    new_is_private: bool | None = None
    permanent: bool = False
    edited_event: bool = False


class EnableRequest(StrictBaseModel):
    request: Literal["enable"] = "enable"
    id: int
    secret: str | None = None


class DisableRequest(StrictBaseModel):
    request: Literal["disable"] = "disable"
    id: int
    stop_recording: bool = True
    secret: str | None = None


class KickAllRequest(StrictBaseModel):
    request: Literal["kick_all"] = "kick_all"
    id: int
    secret: str | None = None


class RecordingRequest(StrictBaseModel):
    request: Literal["recording"] = "recording"
    action: Literal["start", "stop"]
    id: int
    media: list[RecordingMedia] = Field(default_factory=list)


class WatchRequest(StrictBaseModel):
    request: Literal["watch"] = "watch"
    id: int
    pin: str | None = None
    media: list[str] = Field(default_factory=list)
    offer_audio: bool | None = None
    offer_video: bool | None = None
    offer_data: bool | None = None


class StartRequest(StrictBaseModel):
    request: Literal["start"] = "start"


class PauseRequest(StrictBaseModel):
    request: Literal["pause"] = "pause"


class ConfigureRequest(StrictBaseModel):
    request: Literal["configure"] = "configure"
    streams: list[ConfigureStream] = Field(default_factory=list)
    audio: bool | None = None
    video: bool | None = None
    data: bool | None = None


class SwitchRequest(StrictBaseModel):
    request: Literal["switch"] = "switch"
    id: int


class StopRequest(StrictBaseModel):
    request: Literal["stop"] = "stop"


StreamingRequest = Union[
    ListRequest,
    InfoRequest,
    CreateRequest,
    DestroyRequest,
    EditRequest,
    EnableRequest,
    DisableRequest,
    KickAllRequest,
    RecordingRequest,
    WatchRequest,
    StartRequest,
    PauseRequest,
    ConfigureRequest,
    SwitchRequest,
    StopRequest,
]


class MediaSummary(StrictBaseModel):
    mid: str
    label: str | None = None
    msid: str | None = None
    type: TrackType
    age_ms: int | None = Field(default=None, ge=0)


class MediaInfo(MediaSummary):
    mindex: int | None = Field(default=None, ge=0)
    pt: int | None = Field(default=None, ge=0, le=127)
    codec: str | None = None
    rtpmap: str | None = None
    fmtp: str | None = None


class MountPointSummary(StrictBaseModel):
    id: int
    type: MountpointType
    description: str | None = None
    metadata: str | None = None
    enabled: bool | None = None
    media: list[MediaSummary] = Field(default_factory=list)


class MountPointInfo(StrictBaseModel):
    id: int
    name: str | None = None
    description: str | None = None
    metadata: str | None = None
    secret: str | None = None
    pin: str | None = None
    is_private: bool | None = None
    viewers: int | None = Field(default=None, ge=0)
    enabled: bool | None = None
    type: MountpointType
    media: list[MediaInfo] = Field(default_factory=list)


class CreatedPort(StrictBaseModel):
    type: TrackType
    mid: str
    msid: str | None = None
    port: int = Field(..., ge=1, le=65535)


class CreatedMountPoint(StrictBaseModel):
    id: int
    type: MountpointType
    description: str | None = None
    is_private: bool | None = None
    ports: list[CreatedPort] = Field(default_factory=list)


class ListResponse(StrictBaseModel):
    mountpoints: list[MountPointSummary] = Field(alias="list", default_factory=list)


class InfoResponse(StrictBaseModel):
    mountpoint: MountPointInfo = Field(alias="info")


class CreatedResponse(StrictBaseModel):
    create: str
    permanent: bool = False
    stream: CreatedMountPoint


class EditedResponse(StrictBaseModel):
    id: int
    permanent: bool | None = None
    metadata: str | None = None


class DestroyedResponse(StrictBaseModel):
    id: int


class OkResponse(StrictBaseModel):
    streaming: Literal["ok"] = "ok"


class KickedAllResponse(StrictBaseModel):
    streaming: Literal["kicked_all"] = "kicked_all"


class PreparingResponse(StrictBaseModel):
    status: Literal["preparing"] = "preparing"
    jsep: JanusJsep | None = None


class StartingResponse(StrictBaseModel):
    status: Literal["starting"] = "starting"
    jsep: JanusJsep | None = None


class PausingResponse(StrictBaseModel):
    status: Literal["pausing"] = "pausing"


class StoppingResponse(StrictBaseModel):
    status: Literal["stopping"] = "stopping"


class SwitchedResponse(StrictBaseModel):
    switched: Literal["ok"] = "ok"
    id: int


StreamingResponse = Union[
    ListResponse,
    InfoResponse,
    CreatedResponse,
    EditedResponse,
    DestroyedResponse,
    OkResponse,
    KickedAllResponse,
    PreparingResponse,
    StartingResponse,
    PausingResponse,
    StoppingResponse,
    SwitchedResponse,
]


__all__ = (
    "AudioTrack",
    "ConfigureRequest",
    "ConfigureStream",
    "CreateAudioMedia",
    "CreateDataMedia",
    "CreateMedia",
    "CreateMediaBase",
    "CreateRequest",
    "CreateVideoMedia",
    "CreatedMountPoint",
    "CreatedPort",
    "CreatedResponse",
    "DataTrack",
    "DestroyRequest",
    "DestroyedResponse",
    "DisableRequest",
    "EditRequest",
    "EditedResponse",
    "EnableRequest",
    "InfoRequest",
    "InfoResponse",
    "KickAllRequest",
    "KickedAllResponse",
    "ListRequest",
    "ListResponse",
    "MediaInfo",
    "MediaStream",
    "MediaSummary",
    "MountPoint",
    "MountPointInfo",
    "MountPointSummary",
    "MountpointType",
    "OkResponse",
    "PauseRequest",
    "PausingResponse",
    "PreparingResponse",
    "RecordingMedia",
    "RecordingRequest",
    "StartRequest",
    "StartingResponse",
    "StopRequest",
    "StoppingResponse",
    "StreamingRequest",
    "StreamingResponse",
    "SwitchRequest",
    "SwitchedResponse",
    "Track",
    "WatchRequest",
)
