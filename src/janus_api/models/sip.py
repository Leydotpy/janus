from __future__ import annotations

"""Pydantic models for the Janus SIP plugin.

The SIP plugin is asynchronous according to the Janus documentation: requests
are acknowledged through plugin events tied to the same transaction.

Notes:
- These models cover the plugin body and documented event payloads.
- JSEP, when required, belongs to the outer Janus message and is represented
  here on responses via the optional `jsep` field.
- A couple of actions listed by the docs (`dtmf_info`, `unsubscribe`) are
  modeled conservatively because the page names them but does not provide the
  same fully expanded request/response examples that it provides for most
  other SIP actions.
"""

from typing import Annotated, Literal, Union

from pydantic import Field

from .common import HeadersMap, JanusJsep, LooseBaseModel, PluginErrorResponse, StrictBaseModel


class SipRegisterRequest(StrictBaseModel):
    """Register a SIP identity, or start using one in guest/helper mode.

    Janus documents that `register` may or may not result in an actual SIP
    REGISTER depending on `type`, `send_register`, guest mode, or helper mode.
    Successful completion yields a `registered` event; failures yield
    `registration_failed`.
    """

    request: Literal["register"] = "register"
    type: Literal["guest", "helper"] | None = None
    send_register: bool | None = None
    force_udp: bool | None = None
    force_tcp: bool | None = None
    sips: bool | None = None
    rfc2543_cancel: bool | None = None
    automatic_ringing: bool | None = None
    username: str
    secret: str | None = None
    ha1_secret: str | None = None
    authuser: str | None = None
    display_name: str | None = None
    user_agent: str | None = None
    proxy: str | None = None
    outbound_proxy: str | None = None
    headers: HeadersMap | None = None
    contact_params: list[HeadersMap] | None = None
    incoming_header_prefixes: list[str] | None = None
    refresh: bool | None = None
    master_id: int | None = None
    register_ttl: int | None = None


class SipUnregisterRequest(StrictBaseModel):
    """Unregister the current SIP account.

    Janus lists `unregister` as a supported asynchronous SIP request.
    """

    request: Literal["unregister"] = "unregister"


class SipCallRequest(StrictBaseModel):
    """Send an INVITE to a SIP peer.

    Janus requires this request to be associated with a JSEP offer in the
    outer Janus message.
    """

    request: Literal["call"] = "call"
    uri: str | None = None
    autoaccept_reinvites: bool | None = None
    call_id: str | None = None
    refer_id: str | None = None
    srtp: Literal["sdes_optional", "sdes_mandatory"] | None = None
    srtp_profile: str | None = None
    headers: HeadersMap | None = None


class SipProgressRequest(StrictBaseModel):
    """Send a 183 Session Progress response for an incoming INVITE.

    Janus documents this as optional and used for early media when handling an
    incoming call.
    """

    request: Literal["progress"] = "progress"
    srtp: Literal["sdes_optional", "sdes_mandatory"] | None = None
    headers: HeadersMap | None = None


class SipAcceptRequest(StrictBaseModel):
    """Accept an incoming INVITE.

    Janus expects this to carry the callee's JSEP answer in the outer Janus
    message.
    """

    request: Literal["accept"] = "accept"
    srtp: Literal["sdes_optional", "sdes_mandatory"] | None = None
    headers: HeadersMap | None = None


class SipUpdateRequest(StrictBaseModel):
    """Renegotiate an existing SIP session.

    The docs explain that `update` is used for re-INVITEs and ICE restarts
    rather than `call`.
    """

    request: Literal["update"] = "update"


class SipDeclineRequest(StrictBaseModel):
    """Reject an incoming call.

    Janus documents status- and reason-oriented parameters for declining a SIP
    INVITE.
    """

    request: Literal["decline"] = "decline"
    code: int | None = None
    reason: str | None = None
    headers: HeadersMap | None = None


class SipHoldRequest(StrictBaseModel):
    """Put the current SIP call on hold."""

    request: Literal["hold"] = "hold"
    direction: Literal["sendonly", "recvonly", "inactive"] | None = None


class SipUnholdRequest(StrictBaseModel):
    """Resume media after a previous hold."""

    request: Literal["unhold"] = "unhold"


class SipHangupRequest(StrictBaseModel):
    """Terminate, cancel, or reject the current SIP interaction."""

    request: Literal["hangup"] = "hangup"
    headers: HeadersMap | None = None


class SipMessageRequest(StrictBaseModel):
    """Send a SIP MESSAGE request."""

    request: Literal["message"] = "message"
    call_id: str | None = None
    content_type: str | None = Field(default=None, alias="content_type")
    content: str
    uri: str | None = None
    headers: HeadersMap | None = None


class SipInfoRequest(StrictBaseModel):
    """Send a SIP INFO request."""

    request: Literal["info"] = "info"
    type: str
    content: str
    headers: HeadersMap | None = None


class SipDtmfInfoRequest(LooseBaseModel):
    """Send DTMF using SIP INFO.

    The official SIP plugin page lists `dtmf_info` as a supported request and
    describes it conceptually, but it does not provide the same explicit JSON
    schema example it provides for many other requests. This model therefore
    remains intentionally permissive.
    """

    request: Literal["dtmf_info"] = "dtmf_info"
    digit: str | None = None
    duration: int | None = None
    headers: HeadersMap | None = None


class SipSubscribeRequest(StrictBaseModel):
    """Send a SIP SUBSCRIBE request and start receiving NOTIFY events."""

    request: Literal["subscribe"] = "subscribe"
    call_id: str | None = None
    event: str
    accept: str | None = None
    to: str | None = None
    subscribe_ttl: int | None = None
    content: str | None = None
    content_type: str | None = None
    headers: list[HeadersMap] | None = None


class SipUnsubscribeRequest(LooseBaseModel):
    """End a SIP event subscription.

    The Janus page lists `unsubscribe` among supported requests but does not
    provide a fully expanded example payload alongside the `subscribe`
    documentation. This model stays permissive for that reason.
    """

    request: Literal["unsubscribe"] = "unsubscribe"
    call_id: str | None = None
    event: str | None = None
    to: str | None = None


class SipTransferRequest(LooseBaseModel):
    """Initiate a blind or attended SIP transfer.

    The SIP docs describe `transfer` conceptually. The precise payload may vary
    by transfer style and implementation details, so the model accepts extra
    fields while still naming the request.
    """

    request: Literal["transfer"] = "transfer"
    uri: str | None = None
    replace: str | None = None
    refer_id: str | None = None
    headers: HeadersMap | None = None


class SipRecordingRequest(StrictBaseModel):
    """Start or stop SIP-side call recording.

    The SIP docs describe this in the same style as the NoSIP plugin: local
    and peer audio/video can be selected independently.
    """

    request: Literal["recording"] = "recording"
    action: Literal["start", "stop"]
    audio: bool | None = None
    video: bool | None = None
    peer_audio: bool | None = None
    peer_video: bool | None = None
    filename: str | None = None


class SipKeyframeRequest(StrictBaseModel):
    """Request a keyframe from the WebRTC side, the SIP side, or both."""

    request: Literal["keyframe"] = "keyframe"
    user: bool | None = None
    peer: bool | None = None


class SipForwardStreamRequest(StrictBaseModel):
    """One RTP forwarder stream entry for the SIP plugin."""

    type: Literal["audio", "video", "peer_audio", "peer_video"]
    host: str
    host_family: Literal["ipv4", "ipv6"] | None = None
    port: int
    ssrc: int | None = None
    pt: int | None = None
    srtp_suite: Literal[32, 80] | None = None
    srtp_crypto: str | None = None


class SipRtpForwardRequest(StrictBaseModel):
    """Create one or more RTP forwarders for the active SIP call."""

    request: Literal["rtp_forward"] = "rtp_forward"
    streams: list[SipForwardStreamRequest]


class SipStopRtpForwardRequest(StrictBaseModel):
    """Destroy one RTP forwarder created for the active SIP call."""

    request: Literal["stop_rtp_forward"] = "stop_rtp_forward"
    stream_id: int


class SipListForwardersRequest(StrictBaseModel):
    """List RTP forwarders for the active SIP call."""

    request: Literal["listforwarders"] = "listforwarders"


SipRequest = Annotated[
    Union[
        SipRegisterRequest,
        SipUnregisterRequest,
        SipCallRequest,
        SipProgressRequest,
        SipAcceptRequest,
        SipUpdateRequest,
        SipDeclineRequest,
        SipHoldRequest,
        SipUnholdRequest,
        SipHangupRequest,
        SipMessageRequest,
        SipInfoRequest,
        SipDtmfInfoRequest,
        SipSubscribeRequest,
        SipUnsubscribeRequest,
        SipTransferRequest,
        SipRecordingRequest,
        SipKeyframeRequest,
        SipRtpForwardRequest,
        SipStopRtpForwardRequest,
        SipListForwardersRequest,
    ],
    Field(discriminator="request"),
]


class SipEventBase(StrictBaseModel):
    """Base result payload for documented SIP events."""

    event: str
    headers: HeadersMap | None = None


class SipRegisteredResult(SipEventBase):
    """Successful registration event."""

    event: Literal["registered"]
    username: str
    register_sent: bool | None = None
    master_id: int | None = None


class SipRegistrationFailedResult(SipEventBase):
    """Definitive registration failure event."""

    event: Literal["registration_failed"]
    code: int
    reason: str


class SipCallingResult(SipEventBase):
    """Acknowledges that Janus started an outgoing INVITE transaction."""

    event: Literal["calling"]


class SipIncomingCallResult(SipEventBase):
    """Incoming INVITE notification.

    The docs show the caller identity and optional display name and refer id,
    with JSEP offer attached on the outer event when appropriate.
    """

    event: Literal["incomingcall"]
    username: str
    displayname: str | None = None
    referred_by: str | None = None
    refer_id: str | None = None
    srtp: Literal["sdes_optional", "sdes_mandatory"] | None = None


class SipRingingResult(SipEventBase):
    """180 Ringing event for an outgoing call."""

    event: Literal["ringing"]


class SipProgressResult(SipEventBase):
    """183 Session Progress event for early media."""

    event: Literal["progress"]
    username: str | None = None


class SipAcceptedResult(SipEventBase):
    """Successful call acceptance event."""

    event: Literal["accepted"]
    username: str | None = None


class SipUpdateResult(SipEventBase):
    """Session-update notification."""

    event: Literal["updating", "update"]


class SipHoldingResult(SipEventBase):
    """Hold/unhold progress notification."""

    event: Literal["holding", "resuming", "holdingok", "resumingok"]


class SipHangupResult(SipEventBase):
    """SIP-transaction or call teardown event.

    Janus uses this shape for SIP-layer outcomes such as declines or BYE/CANCEL
    related terminations.
    """

    event: str
    code: int | None = None
    reason: str | None = None
    reason_header: str | None = None
    reason_header_protocol: str | None = None
    reason_header_cause: int | None = None


class SipMessageEventResult(SipEventBase):
    """Incoming SIP MESSAGE notification."""

    event: Literal["message"]
    sender: str
    displayname: str | None = None
    content: str
    content_type: str | None = Field(default=None, alias="content_type")


class SipMessageDeliveryResult(SipEventBase):
    """Delivery result for a previously sent SIP MESSAGE."""

    event: Literal["messagedelivery"]
    code: int
    reason: str


class SipInfoEventResult(SipEventBase):
    """Incoming SIP INFO notification."""

    event: Literal["info"]
    sender: str
    displayname: str | None = None
    type: str
    content: str


class SipInfoSentResult(SipEventBase):
    """Confirmation that a SIP INFO was sent."""

    event: Literal["infosent"]


class SipNotifyResult(SipEventBase):
    """Incoming SIP NOTIFY event."""

    event: Literal["notify"]
    notify: str
    substate: str
    content: str
    content_type: str | None = Field(default=None, alias="content-type")


class SipSubscribeStatusResult(SipEventBase):
    """Subscription transaction status event."""

    event: Literal["subscribing", "subscribe_succeeded", "subscribe_failed"]


class SipRecordingUpdatedResult(SipEventBase):
    """Confirmation that recording state changed."""

    event: Literal["recordingupdated"]


class SipKeyframeSentResult(SipEventBase):
    """Confirmation that a keyframe request was sent."""

    event: Literal["keyframesent"]


class SipForwarder(StrictBaseModel):
    """RTP forwarder descriptor returned by the SIP plugin."""

    stream_id: int
    type: Literal["audio", "video", "peer_audio", "peer_video"]
    host: str
    port: int
    media: Literal["audio", "video"]
    ssrc: int | None = None
    pt: int | None = None
    srtp: bool | None = None


class SipRtpForwardResult(SipEventBase):
    """Result payload for `rtp_forward`."""

    event: Literal["rtp_forward"]
    forwarders: list[SipForwarder]


class SipStopRtpForwardResult(SipEventBase):
    """Result payload for `stop_rtp_forward`."""

    event: Literal["stop_rtp_forward"]
    stream_id: int


class SipForwardersResult(SipEventBase):
    """Result payload for `listforwarders`."""

    event: Literal["forwarders"]
    forwarders: list[SipForwarder]


class SipTransferStatusResult(SipEventBase):
    """Transfer-related status event.

    The official page documents transfer support conceptually; the exact event
    naming can vary, so this model intentionally stays slightly broader.
    """

    event: Literal["transferring", "transferaccepted", "transferfailed", "transfer"]


SipResult = Union[
    SipRegisteredResult,
    SipRegistrationFailedResult,
    SipCallingResult,
    SipIncomingCallResult,
    SipRingingResult,
    SipProgressResult,
    SipAcceptedResult,
    SipUpdateResult,
    SipHoldingResult,
    SipHangupResult,
    SipMessageEventResult,
    SipMessageDeliveryResult,
    SipInfoEventResult,
    SipInfoSentResult,
    SipNotifyResult,
    SipSubscribeStatusResult,
    SipRecordingUpdatedResult,
    SipKeyframeSentResult,
    SipRtpForwardResult,
    SipStopRtpForwardResult,
    SipForwardersResult,
    SipTransferStatusResult,
]


class SipEventResponse(StrictBaseModel):
    """Asynchronous SIP plugin response/event."""

    sip: Literal["event"]
    call_id: str | None = None
    master_id: int | None = None
    result: SipResult
    jsep: JanusJsep | None = None


class SipErrorResponse(PluginErrorResponse):
    """Plugin-level SIP error response."""

    sip: Literal["event"]


SipResponse = Union[
    SipEventResponse,
    SipErrorResponse,
]
