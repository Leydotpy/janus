from __future__ import annotations

"""Pydantic models for the Janus TextRoom plugin.

The TextRoom plugin has two documented surfaces:

1. Janus API messages such as `setup`, `ack`, `restart`, and room-management
   operations.
2. DataChannel messages, where each request uses a `textroom` property and a
   mandatory `transaction`.

These models cover both surfaces and the documented asynchronous room/chat
events.
"""

from typing import Annotated, Literal, Union, Iterable

from pydantic import Field, model_validator

from .common import JanusJsep, PluginErrorResponse, StrictBaseModel, TransactionalDataMessage


class TextRoomRoomSummary(StrictBaseModel):
    """Room summary returned by `list`."""

    room: int
    description: str
    pin_required: bool | None = None
    num_participants: int | None = None
    history: int | None = None


class TextRoomParticipant(StrictBaseModel):
    """Participant entry used in participant lists and join responses/events."""

    username: str
    display: str | None = None


class TextRoomSetupRequest(StrictBaseModel):
    """Initialize the PeerConnection/data channel for TextRoom.

    Janus documents `setup` as the typical Janus-API message sent before all
    DataChannel traffic. The asynchronous response is a `textroom: event`
    carrying `result: ok` and usually a JSEP offer.
    """

    request: Literal["setup"] = "setup"


class TextRoomAckRequest(StrictBaseModel):
    """Complete the PeerConnection setup or ICE restart.

    Janus documents `ack` as an empty Janus-API request that is sent with the
    application's JSEP answer after a `setup` or `restart` offer.
    """

    request: Literal["ack"] = "ack"


class TextRoomRestartRequest(StrictBaseModel):
    """Request an ICE restart for the TextRoom PeerConnection.

    Janus answers asynchronously with a new JSEP offer. The client then uses
    `ack` to provide its answer.
    """

    request: Literal["restart"] = "restart"


class TextRoomJanusListParticipantsRequest(StrictBaseModel):
    """List participants in a room via the Janus API surface."""

    request: Literal["listparticipants"] = "listparticipants"
    room: int


class TextRoomDataListRequest(TransactionalDataMessage):
    """List public rooms over the DataChannel API."""

    textroom: Literal["list"] = "list"
    admin_key: str | None = None


class TextRoomDataCreateRequest(TransactionalDataMessage):
    """Create a room through the TextRoom DataChannel API.

    Janus documents that room-management requests are also available through
    the Janus API if `request` is used instead of `textroom`.
    """

    textroom: Literal["create"] = "create"
    room: int | None = None
    admin_key: str | None = None
    description: str | None = None
    secret: str | None = None
    pin: str | None = None
    is_private: bool | None = None
    history: int | None = None
    post: str | None = None
    permanent: bool | None = None


class TextRoomDataEditRequest(TransactionalDataMessage):
    """Edit mutable room properties."""

    textroom: Literal["edit"] = "edit"
    room: int
    secret: str
    new_description: str | None = None
    new_secret: str | None = None
    new_pin: str | None = None
    new_is_private: bool | None = None
    permanent: bool | None = None


class TextRoomDataDestroyRequest(TransactionalDataMessage):
    """Destroy a room.

    Janus replies with `destroyed`, and room members receive a `destroyed`
    event as well.
    """

    textroom: Literal["destroy"] = "destroy"
    room: int
    secret: str
    permanent: bool | None = None


class TextRoomDataExistsRequest(TransactionalDataMessage):
    """Check whether a room exists."""

    textroom: Literal["exists"] = "exists"
    room: int


class TextRoomDataAllowedRequest(TransactionalDataMessage):
    """Enable/disable or modify room ACL tokens."""

    textroom: Literal["allowed"] = "allowed"
    secret: str
    action: Literal["enable", "disable", "add", "remove"]
    room: int
    allowed: list[str] | None = None


class TextRoomDataKickRequest(TransactionalDataMessage):
    """Kick a participant from a room."""

    textroom: Literal["kick"] = "kick"
    secret: str
    room: int
    username: str


class TextRoomJoinRequest(TransactionalDataMessage):
    """Join a room over the TextRoom DataChannel API.

    Janus returns a `success` response with the current participants. Other
    members receive a `join` event.
    """

    textroom: Literal["join"] = "join"
    room: int
    pin: str | None = None
    username: str
    display: str | None = None
    token: str | None = None
    history: bool | None = None


class TextRoomLeaveRequest(TransactionalDataMessage):
    """Leave a room over the DataChannel API."""

    textroom: Literal["leave"] = "leave"
    room: int


class TextRoomMessageRequest(TransactionalDataMessage):
    """Send a public or private room message.

    A message with neither `to` nor `tos` is public. The docs state that
    `to` and `tos` are mutually exclusive. When `ack` is true, Janus returns
    a `success` response on delivery.
    """

    textroom: Literal["message"] = "message"
    room: int
    to: str | None = None
    tos: list[str] | None = None
    text: str
    ack: bool | None = None

    @model_validator(mode="after")
    def _validate_targets(self) -> "TextRoomMessageRequest":
        if self.to and self.tos:
            raise ValueError("`to` and `tos` are mutually exclusive.")
        return self


class TextRoomAnnouncementRequest(TransactionalDataMessage):
    """Send a room-wide announcement as the room itself.

    Janus documents this as an admin/room-secret guarded operation. It returns
    `success` and participants receive an `announcement` event.
    """

    textroom: Literal["announcement"] = "announcement"
    room: int
    secret: str
    text: str


TextRoomJanusRequest = Annotated[
    Union[
        TextRoomSetupRequest,
        TextRoomAckRequest,
        TextRoomRestartRequest,
        TextRoomJanusListParticipantsRequest,
    ],
    Field(discriminator="request"),
]

TextRoomDataRequest = Union[
    TextRoomDataListRequest,
    TextRoomDataCreateRequest,
    TextRoomDataEditRequest,
    TextRoomDataDestroyRequest,
    TextRoomDataExistsRequest,
    TextRoomDataAllowedRequest,
    TextRoomDataKickRequest,
    TextRoomJoinRequest,
    TextRoomLeaveRequest,
    TextRoomMessageRequest,
    TextRoomAnnouncementRequest,
]

TextRoomRequest = TextRoomJanusRequest | TextRoomDataRequest


class TextRoomEventOkResponse(StrictBaseModel):
    """Basic asynchronous Janus-API response used for `setup` and `restart`.

    The docs show `textroom: event` with `result: ok`, often accompanied by a
    JSEP offer.
    """

    textroom: Literal["event"]
    result: Literal["ok"]
    jsep: JanusJsep | None = None


class TextRoomSuccessResponse(StrictBaseModel):
    """Generic transactional success response.

    DataChannel requests echo the client `transaction`. The docs omit it in
    examples for brevity, but explicitly say it is always present in request
    responses.
    """

    textroom: Literal["success"]
    transaction: str | None = None
    room: int | None = None
    exists: bool | None = None
    allowed: list[str] | None = None
    rooms: list[TextRoomRoomSummary] | None = Field(default=None, alias="list")
    participants: Iterable[TextRoomParticipant] = Field(default_factory=list)


class TextRoomEditedResponse(StrictBaseModel):
    """Response to an `edit` request."""

    textroom: Literal["edited"]
    transaction: str | None = None
    room: int
    permanent: bool | None = None


class TextRoomDestroyedResponse(StrictBaseModel):
    """Response to `destroy` or unsolicited room-destroyed event."""

    textroom: Literal["destroyed"]
    transaction: str | None = None
    room: int
    permanent: bool | None = None


class TextRoomJoinEvent(StrictBaseModel):
    """Unsolicited room event announcing that someone joined."""

    textroom: Literal["join"]
    room: int
    username: str
    display: str | None = None


class TextRoomLeaveEvent(StrictBaseModel):
    """Unsolicited room event announcing that someone left."""

    textroom: Literal["leave"]
    room: int
    username: str


class TextRoomKickedEvent(StrictBaseModel):
    """Unsolicited room event announcing that someone was kicked."""

    textroom: Literal["kicked"]
    room: int
    username: str


class TextRoomMessageEvent(StrictBaseModel):
    """Incoming public or private room message.

    Janus documents `whisper=true` for private messages delivered to the user.
    """

    textroom: Literal["message"]
    room: int
    from_: str = Field(alias="from")
    date: str
    text: str
    whisper: bool | None = None


class TextRoomAnnouncementEvent(StrictBaseModel):
    """Incoming room announcement.

    The shape is the same as a message event but without `from`, because the
    room itself is the sender.
    """

    textroom: Literal["announcement"]
    room: int
    date: str
    text: str


class TextRoomErrorResponse(PluginErrorResponse):
    """Plugin-level TextRoom error response."""

    textroom: str


TextRoomResponse = Union[
    TextRoomEventOkResponse,
    TextRoomSuccessResponse,
    TextRoomEditedResponse,
    TextRoomDestroyedResponse,
    TextRoomJoinEvent,
    TextRoomLeaveEvent,
    TextRoomKickedEvent,
    TextRoomMessageEvent,
    TextRoomAnnouncementEvent,
    TextRoomErrorResponse,
]
