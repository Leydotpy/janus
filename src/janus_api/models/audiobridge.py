from __future__ import annotations

"""Pydantic models for the Janus AudioBridge plugin.

Scope:
- Synchronous room-management and RTP-forwarding requests/responses.
- Asynchronous participation requests such as `join`, `configure`, `leave`,
  and `changeroom`.
- Announcement playback requests and events.

The models represent the plugin body documented by Janus. If you are sending
these through the Janus core API, wrap them in your own transport/session
envelope and attach `jsep` separately where needed.
"""

from typing import Annotated, Literal, Union, Iterable

from pydantic import Field

from .common import JanusJsep, PluginErrorResponse, StrictBaseModel


class AudioBridgeRoomSummary(StrictBaseModel):
    """Summary of an AudioBridge room as returned by `list`.

    Janus returns these objects inside a `rooms` array when a `list` request
    succeeds.
    """

    room: int
    description: str
    pin_required: bool | None = None
    sampling_rate: int | None = None
    spatial_audio: bool | None = None
    record: bool | None = None
    num_participants: int | None = None


class AudioBridgeParticipant(StrictBaseModel):
    """Participant snapshot used in participant lists and participant updates.

    Janus includes participant objects in `joined` events, `listparticipants`
    responses, and some room notifications such as mute/suspend/resume updates.
    """

    id: int
    display: str | None = None
    setup: bool | None = None
    muted: bool | None = None
    suspended: bool | None = None
    talking: bool | None = None
    spatial_position: int | None = None
    group: str | None = None


class AudioBridgeRtpJoinInfo(StrictBaseModel):
    """Plain-RTP transport information used by RTP participants.

    Janus uses this shape when a participant joins over plain RTP rather than
    WebRTC, and it may also echo the negotiated transport details back in the
    corresponding `joined` event.
    """

    ip: str
    port: int
    payload_type: int | None = None
    audiolevel_ext: int | None = None
    fec: bool | None = None


class AudioBridgeForwarder(StrictBaseModel):
    """RTP forwarder description returned by AudioBridge.

    Janus returns these objects when a forwarder is created or listed.
    """

    stream_id: int
    group: str | None = None
    ip: str | None = None
    host: str | None = None
    port: int
    ssrc: int | None = None
    codec: str | None = None
    ptype: int | None = None
    srtp: bool | None = None
    always_on: bool | None = None


class AudioBridgeAnnouncement(StrictBaseModel):
    """Announcement/playback entry returned by `listannouncements`.

    AudioBridge only plays filesystem `.opus` files for announcements according
    to the Janus plugin documentation.
    """

    file_id: str
    filename: str
    playing: bool
    loop: bool | None = None


class AudioBridgeCreateRequest(StrictBaseModel):
    """Create a room dynamically.

    This is a synchronous request. On success Janus replies with a `created`
    response containing the room id and whether persistence succeeded.
    """

    request: Literal["create"] = "create"
    room: int | None = None
    permanent: bool | None = None
    description: str | None = None
    secret: str | None = None
    pin: str | None = None
    is_private: bool | None = None
    allowed: list[str] | None = None
    sampling_rate: int | None = None
    spatial_audio: bool | None = None
    audiolevel_ext: bool | None = None
    audiolevel_event: bool | None = None
    audio_active_packets: int | None = None
    audio_level_average: int | None = None
    default_expectedloss: int | None = None
    default_bitrate: int | None = None
    denoise: bool | None = None
    record: bool | None = None
    record_file: str | None = None
    record_dir: str | None = None
    mjrs: bool | None = None
    mjrs_dir: str | None = None
    allow_rtp_participants: bool | None = None
    groups: list[str] | None = None
    admin_key: str | None = None


class AudioBridgeEditRequest(StrictBaseModel):
    """Edit mutable room properties.

    Janus documents `edit` as synchronous and replies with an `edited`
    response containing the room id.
    """

    request: Literal["edit"] = "edit"
    room: int
    secret: str
    new_description: str | None = None
    new_secret: str | None = None
    new_pin: str | None = None
    new_is_private: bool | None = None
    new_record_dir: str | None = None
    new_mjrs_dir: str | None = None
    permanent: bool | None = None


class AudioBridgeDestroyRequest(StrictBaseModel):
    """Destroy a room.

    Janus replies synchronously with `destroyed`. Existing participants also
    receive a `destroyed` event.
    """

    request: Literal["destroy"] = "destroy"
    room: int
    secret: str
    permanent: bool | None = None


class AudioBridgeEnableRecordingRequest(StrictBaseModel):
    """Enable or disable mixed WAV recording for the room.

    The Janus page documents this as a synchronous admin request.
    """

    request: Literal["enable_recording"] = "enable_recording"
    room: int
    secret: str
    record: bool
    record_file: str | None = None
    record_dir: str | None = None


class AudioBridgeEnableMjrsRequest(StrictBaseModel):
    """Enable or disable per-participant MJR recording in bulk.

    Janus documents this separately from mixed-room recording.
    """

    request: Literal["enable_mjrs"] = "enable_mjrs"
    room: int
    secret: str
    mjrs: bool
    mjrs_dir: str | None = None


class AudioBridgeExistsRequest(StrictBaseModel):
    """Check whether a room exists.

    Janus replies synchronously with a `success` response carrying `exists`.
    """

    request: Literal["exists"] = "exists"
    room: int


class AudioBridgeAllowedRequest(StrictBaseModel):
    """Enable, disable, add, or remove room ACL tokens.

    Janus replies synchronously with the updated full `allowed` token list for
    the actions that manipulate or enable the ACL.
    """

    request: Literal["allowed"] = "allowed"
    secret: str
    action: Literal["enable", "disable", "add", "remove"]
    room: int
    allowed: list[str] | None = None


class AudioBridgeKickRequest(StrictBaseModel):
    """Kick one participant from a room.

    This does not ban re-entry by itself; Janus documents ACL removal as the
    way to prevent a kicked user from rejoining.
    """

    request: Literal["kick"] = "kick"
    secret: str
    room: int
    id: int


class AudioBridgeKickAllRequest(StrictBaseModel):
    """Kick all participants from a room.

    Janus documents this as a synchronous admin request returning `success`.
    """

    request: Literal["kick_all"] = "kick_all"
    secret: str
    room: int


class AudioBridgeSuspendRequest(StrictBaseModel):
    """Suspend a participant without destroying the PeerConnection.

    Janus documents that a suspended participant is removed from the mix and,
    optionally, room events can be paused until a later `resume`.
    """

    request: Literal["suspend"] = "suspend"
    secret: str
    room: int
    id: int
    pause_events: bool | None = None
    stop_record: bool | None = None


class AudioBridgeResumeRequest(StrictBaseModel):
    """Resume a previously suspended participant.

    Janus returns `success`, and other room members are notified that the
    participant resumed.
    """

    request: Literal["resume"] = "resume"
    secret: str
    room: int
    id: int
    record: bool | None = None
    filename: str | None = None


class AudioBridgeListRequest(StrictBaseModel):
    """List public rooms.

    Janus returns a synchronous `success` response with a `rooms` array.
    """

    request: Literal["list"] = "list"


class AudioBridgeListParticipantsRequest(StrictBaseModel):
    """List participants in a specific room.

    Janus returns a `participants` response containing participant objects.
    """

    request: Literal["listparticipants"] = "listparticipants"
    room: int


class AudioBridgeResetDecoderRequest(StrictBaseModel):
    """Reset the current participant's Opus decoder state.

    Janus documents this as a synchronous `success` response.
    """

    request: Literal["resetdecoder"] = "resetdecoder"
    room: int | None = None
    id: int | None = None
    secret: str | None = None


class AudioBridgeMuteRequest(StrictBaseModel):
    """Admin mute a participant.

    Janus also documents the symmetric `unmute` request with the same body
    shape and a `success` response.
    """

    request: Literal["mute"] = "mute"
    secret: str
    room: int
    id: int


class AudioBridgeUnmuteRequest(StrictBaseModel):
    """Admin unmute a participant.

    This mirrors `mute` and returns a synchronous `success` response.
    """

    request: Literal["unmute"] = "unmute"
    secret: str
    room: int
    id: int


class AudioBridgeMuteRoomRequest(StrictBaseModel):
    """Mute the whole room.

    Janus documents the symmetric `unmute_room` request with the same payload
    shape and a `success` response.
    """

    request: Literal["mute_room"] = "mute_room"
    secret: str
    room: int


class AudioBridgeUnmuteRoomRequest(StrictBaseModel):
    """Unmute the whole room.

    This mirrors `mute_room`.
    """

    request: Literal["unmute_room"] = "unmute_room"
    secret: str
    room: int


class AudioBridgeRtpForwardRequest(StrictBaseModel):
    """Create a room RTP forwarder.

    Janus replies synchronously with `success` and includes the assigned
    `stream_id`. When groups are enabled, `group` scopes the forwarded mix.
    """

    request: Literal["rtp_forward"] = "rtp_forward"
    room: int
    group: str | None = None
    ssrc: int | None = None
    codec: str | None = None
    ptype: int | None = None
    host: str
    host_family: Literal["ipv4", "ipv6"] | None = None
    port: int
    srtp_suite: Literal[32, 80] | None = None
    srtp_crypto: str | None = None
    always_on: bool | None = None
    admin_key: str | None = None


class AudioBridgeStopRtpForwardRequest(StrictBaseModel):
    """Stop a previously created RTP forwarder.

    Janus replies synchronously with `success`, echoing the room and
    `stream_id`.
    """

    request: Literal["stop_rtp_forward"] = "stop_rtp_forward"
    room: int
    stream_id: int


class AudioBridgeListForwardersRequest(StrictBaseModel):
    """List forwarders for a room.

    Janus returns a `forwarders` response with `rtp_forwarders`.
    """

    request: Literal["listforwarders"] = "listforwarders"
    room: int


class AudioBridgePlayFileRequest(StrictBaseModel):
    """Play a local `.opus` file in a room.

    Janus replies with `success` and later emits `announcement-started` and
    `announcement-stopped` events as playback changes state.
    """

    request: Literal["play_file"] = "play_file"
    room: int
    secret: str
    group: str | None = None
    file_id: str | None = None
    filename: str
    loop: bool | None = None
    admin_key: str | None = None


class AudioBridgeIsPlayingRequest(StrictBaseModel):
    """Check if a specific announcement is still playing.

    Janus replies with `success` and a `playing` boolean.
    """

    request: Literal["is_playing"] = "is_playing"
    room: int
    secret: str
    file_id: str


class AudioBridgeListAnnouncementsRequest(StrictBaseModel):
    """List announcement/playback entries for a room.

    Janus returns an `announcements` response.
    """

    request: Literal["listannouncements"] = "listannouncements"
    secret: str
    room: int


class AudioBridgeStopFileRequest(StrictBaseModel):
    """Stop a specific announcement/playback entry.

    Janus replies synchronously with `success`.
    """

    request: Literal["stop_file"] = "stop_file"
    room: int
    secret: str
    file_id: str


class AudioBridgeStopAllFilesRequest(StrictBaseModel):
    """Stop all playback entries in a room.

    Janus replies with `success` and a `file_id_list` of interrupted
    announcements.
    """

    request: Literal["stop_all_files"] = "stop_all_files"
    room: int
    secret: str


class AudioBridgeJoinRequest(StrictBaseModel):
    """Join a room as a participant.

    This is asynchronous. Janus replies with a `joined` event, optionally with
    participant snapshots and, for plain RTP participants, RTP target details.
    Attach a JSEP offer or answer externally when using WebRTC.
    """

    request: Literal["join"] = "join"
    room: int
    pin: str | None = None
    token: str | None = None
    muted: bool | None = None
    suspended: bool | None = None
    pause_events: bool | None = None
    display: str | None = None
    id: int | None = None
    group: str | None = None
    codec: Literal["opus", "pcma", "pcmu"] | None = None
    bitrate: int | None = None
    quality: int | None = None
    expected_loss: int | None = None
    volume: int | None = None
    spatial_position: int | None = None
    denoise: bool | None = None
    secret: str | None = None
    record: bool | None = None
    filename: str | None = None
    prebuffer: int | None = None
    audio_level_average: int | None = None
    audio_active_packets: int | None = None
    generate_offer: bool | None = None
    rtp: AudioBridgeRtpJoinInfo | None = None


class AudioBridgeConfigureRequest(StrictBaseModel):
    """Change participant media settings.

    Janus documents this as the request used both for the first negotiated
    setup after `join` and later updates such as mute/unmute. If a JSEP
    negotiation is involved, Janus returns an `event` plus JSEP.
    """

    request: Literal["configure"] = "configure"
    muted: bool | None = None
    display: str | None = None
    bitrate: int | None = None
    quality: int | None = None
    expected_loss: int | None = None
    volume: int | None = None
    spatial_position: int | None = None
    denoise: bool | None = None
    record: bool | None = None
    filename: str | None = None
    group: str | None = None


class AudioBridgeLeaveRequest(StrictBaseModel):
    """Leave the current room.

    Janus sends the leaving participant a `left` event and notifies the rest
    of the room with an `event` that contains `leaving`.
    """

    request: Literal["leave"] = "leave"


class AudioBridgeChangeRoomRequest(StrictBaseModel):
    """Move directly from the current room to another one.

    Janus documents this as essentially a `join`-like request that reuses the
    existing PeerConnection and therefore should not carry a new JSEP payload.
    """

    request: Literal["changeroom"] = "changeroom"
    room: int
    id: int | None = None
    pin: str | None = None
    group: str | None = None
    display: str | None = None
    token: str | None = None
    muted: bool | None = None
    suspended: bool | None = None
    pause_events: bool | None = None
    bitrate: int | None = None
    quality: int | None = None
    expected_loss: int | None = None
    volume: int | None = None
    spatial_position: int | None = None
    denoise: bool | None = None
    record: bool | None = None
    filename: str | None = None


AudioBridgeRequest = Annotated[
    Union[
        AudioBridgeCreateRequest,
        AudioBridgeEditRequest,
        AudioBridgeDestroyRequest,
        AudioBridgeEnableRecordingRequest,
        AudioBridgeEnableMjrsRequest,
        AudioBridgeExistsRequest,
        AudioBridgeAllowedRequest,
        AudioBridgeKickRequest,
        AudioBridgeKickAllRequest,
        AudioBridgeSuspendRequest,
        AudioBridgeResumeRequest,
        AudioBridgeListRequest,
        AudioBridgeListParticipantsRequest,
        AudioBridgeResetDecoderRequest,
        AudioBridgeMuteRequest,
        AudioBridgeUnmuteRequest,
        AudioBridgeMuteRoomRequest,
        AudioBridgeUnmuteRoomRequest,
        AudioBridgeRtpForwardRequest,
        AudioBridgeStopRtpForwardRequest,
        AudioBridgeListForwardersRequest,
        AudioBridgePlayFileRequest,
        AudioBridgeIsPlayingRequest,
        AudioBridgeListAnnouncementsRequest,
        AudioBridgeStopFileRequest,
        AudioBridgeStopAllFilesRequest,
        AudioBridgeJoinRequest,
        AudioBridgeConfigureRequest,
        AudioBridgeLeaveRequest,
        AudioBridgeChangeRoomRequest,
    ],
    Field(discriminator="request"),
]


class AudioBridgeCreatedResponse(StrictBaseModel):
    """Successful response to `create`."""

    audiobridge: Literal["created"]
    room: int
    permanent: bool


class AudioBridgeEditedResponse(StrictBaseModel):
    """Successful response to `edit`."""

    audiobridge: Literal["edited"]
    room: int


class AudioBridgeDestroyedResponse(StrictBaseModel):
    """Room destruction response or room-destroyed event.

    Janus uses `destroyed` both as the direct synchronous response and as the
    unsolicited event pushed to room participants.
    """

    audiobridge: Literal["destroyed"]
    room: int
    permanent: bool | None = None


class AudioBridgeSuccessResponse(StrictBaseModel):
    """Generic synchronous `success` response.

    AudioBridge uses this for many admin and query operations. Extra optional
    fields are included to cover the documented variants.
    """

    audiobridge: Literal["success"]
    room: int | None = None
    exists: bool | None = None
    allowed: list[str] | None = None
    group: str | None = None
    stream_id: int | None = None
    host: str | None = None
    port: int | None = None
    file_id: str | None = None
    file_id_list: list[str] | None = None
    playing: bool | None = None
    permanent: bool | None = None


class AudioBridgeRoomsResponse(StrictBaseModel):
    """Response to `list`."""

    audiobridge: Literal["success"]
    rooms: list[AudioBridgeRoomSummary]


class AudioBridgeParticipantsResponse(StrictBaseModel):
    """Response to `listparticipants`."""

    audiobridge: Literal["participants"]
    room: int
    participants: Iterable[AudioBridgeParticipant] = Field(default_factory=list)


class AudioBridgeForwardersResponse(StrictBaseModel):
    """Response to `listforwarders`."""

    audiobridge: Literal["forwarders"]
    room: int
    rtp_forwarders: list[AudioBridgeForwarder]


class AudioBridgeAnnouncementsResponse(StrictBaseModel):
    """Response to `listannouncements`."""

    audiobridge: Literal["announcements"]
    room: int
    announcements: list[AudioBridgeAnnouncement]


class AudioBridgeJoinedResponse(StrictBaseModel):
    """Asynchronous response to `join` or `changeroom`.

    Janus returns `joined` when the participant has entered the room. The
    response may include currently known participants and may also include RTP
    target details for plain-RTP participants.
    """

    audiobridge: Literal["joined"]
    room: int
    id: int
    display: str | None = None
    participants: list[AudioBridgeParticipant] | None = None
    rtp: AudioBridgeRtpJoinInfo | None = None
    jsep: JanusJsep | None = None


class AudioBridgeRoomChangedResponse(StrictBaseModel):
    """Asynchronous response received after a successful `changeroom`."""

    audiobridge: Literal["roomchanged"]
    room: int
    id: int
    display: str | None = None
    participants: list[AudioBridgeParticipant] | None = None


class AudioBridgeEventResponse(StrictBaseModel):
    """Generic asynchronous `event` response.

    AudioBridge uses `event` for configure success, mute updates, room-change
    notifications, and leave notifications to remaining participants.
    """

    audiobridge: Literal["event"]
    room: int | None = None
    result: str | None = None
    participants: list[AudioBridgeParticipant] | None = None
    leaving: int | None = None
    muted: int | None = None
    suspended: int | None = None
    resumed: int | None = None
    error_code: int | None = None
    error: str | None = None
    jsep: JanusJsep | None = None


class AudioBridgeLeftResponse(StrictBaseModel):
    """Response received by the leaving participant after `leave`."""

    audiobridge: Literal["left"]
    room: int
    id: int


class AudioBridgeAnnouncementStartedEvent(StrictBaseModel):
    """Event sent when playback actually starts in a room."""

    audiobridge: Literal["announcement-started"]
    room: int
    file_id: str


class AudioBridgeAnnouncementStoppedEvent(StrictBaseModel):
    """Event sent when playback stops or is interrupted."""

    audiobridge: Literal["announcement-stopped"]
    room: int
    file_id: str


class AudioBridgeErrorResponse(PluginErrorResponse):
    """Plugin-level AudioBridge error response."""

    audiobridge: Literal["event"]


AudioBridgeResponse = Union[
    AudioBridgeCreatedResponse,
    AudioBridgeEditedResponse,
    AudioBridgeDestroyedResponse,
    AudioBridgeRoomsResponse,
    AudioBridgeParticipantsResponse,
    AudioBridgeForwardersResponse,
    AudioBridgeAnnouncementsResponse,
    AudioBridgeJoinedResponse,
    AudioBridgeRoomChangedResponse,
    AudioBridgeLeftResponse,
    AudioBridgeAnnouncementStartedEvent,
    AudioBridgeAnnouncementStoppedEvent,
    AudioBridgeEventResponse,
    AudioBridgeSuccessResponse,
    AudioBridgeErrorResponse,
]
