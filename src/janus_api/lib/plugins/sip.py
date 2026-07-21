from typing import Any, Literal

from janus_api.lib.plugins.base import Plugin
from janus_api.models.base import Jsep
from janus_api.models.sip import (
    SipRegisterRequest,
    SipUnregisterRequest,
    SipCallRequest,
    SipProgressRequest,
    SipAcceptRequest,
    SipDeclineRequest,
    SipInfoRequest,
    SipMessageRequest,
    SipDtmfInfoRequest,
    SipSubscribeRequest,
    SipUnsubscribeRequest,
    SipTransferRequest,
    SipHangupRequest,
    SipListForwardersRequest,
    SipStopRtpForwardRequest,
    SipRtpForwardRequest,
    SipUpdateRequest,
    SipUnholdRequest,
    SipHoldRequest,
    SipKeyframeRequest,
    SipRecordingRequest,
)


class SipPlugin(Plugin):
    name = 'janus.plugin.sip'
    identifier = 'sip'

    async def register(self, **kwargs):
        return await self.send(SipRegisterRequest(**kwargs))

    async def unregister(self):
        return await self.send(SipUnregisterRequest())

    async def call(self, *, uri: str, sdp: str, sdp_type: Literal["offer", "answer"], **kwargs: Any):
        jsep = Jsep(type=sdp_type, sdp=sdp)
        request = SipCallRequest(uri=uri, **kwargs)
        return await self.send(request, jsep=jsep)

    async def progress(self, *, sdp: str, sdp_type: Literal["offer", "answer"], **kwargs: Any):
        return await self.send(
            SipProgressRequest(**kwargs),
            jsep=Jsep(type=sdp_type, sdp=sdp)
        )

    async def accept(self, *, sdp: str, sdp_type: Literal["offer", "answer"], **kwargs: Any):
        return await self.send(SipAcceptRequest(
            **kwargs
        ),
            jsep=Jsep(sdp=sdp, type=sdp_type)
        )

    async def decline(self, *, code: int | None = None, headers: dict[str, str] | None = None):
        return await self.send(
            SipDeclineRequest(
                code=code,
                headers=headers
            )
        )

    async def info(self, *, content: str, content_type: str, headers: dict[str, str] | None = None):
        return await self.send(
            SipInfoRequest(
                content=content,
                type=content_type,
                headers=headers
            )
        )

    async def message(self, *, content: str, content_type: str | None = None, headers: dict[str, str] | None = None):
        return await self.send(
            SipMessageRequest(
                content_type=content_type, content=content, headers=headers
            )
        )

    async def dtmf_info(self, *, dtmf: str, duration: int | None = None, headers: dict[str, str] | None = None):
        return await self.send(
            SipDtmfInfoRequest(
                duration=duration, headers=headers, digit=dtmf
            )
        )

    async def subscribe(self, *, event: str, call_id: str | None = None, accept: str | None = None,
                        to: str | None = None, subscribe_ttl: int | None = None, content: str | None = None,
                        content_type: str | None = None, headers: list[dict[str, str]] | None = None):
        return await self.send(
            SipSubscribeRequest(
                call_id=call_id,
                event=event,
                accept=accept,
                to=to,
                subscribe_ttl=subscribe_ttl,
                content=content,
                content_type=content_type,
                headers=headers
            )
        )

    async def unsubscribe(self, **kwargs: Any):
        return await self.send(
            SipUnsubscribeRequest(
                **kwargs
            )
        )

    async def transfer(self, *, uri: str, replace: str | None = None):
        return await self.send(
            SipTransferRequest(
                uri=uri,
                replace=replace,
            ),
        )

    async def recording(self, *, action: Literal["start", "stop"], audio: bool | None = None, video: bool | None = None,
                        peer_audio: bool | None = None, peer_video: bool | None = None, file_id: str | None = None):
        return await self.send(SipRecordingRequest(
            action=action,
            audio=audio,
            video=video,
            peer_audio=peer_audio,
            peer_video=peer_video,
            filename=file_id
        ))

    async def keyframe(self):
        return await self.send(SipKeyframeRequest())

    async def hold(self):
        return await self.send(SipHoldRequest())

    async def unhold(self):
        return await self.send(SipUnholdRequest())

    async def update(self, *, sdp: str, sdp_type: Literal["offer", "answer"]):
        return await self.send(SipUpdateRequest(), jsep=Jsep(sdp=sdp, type=sdp_type))

    async def rtp_forward(self, **kwargs: Any):
        return await self.send(SipRtpForwardRequest(**kwargs))

    async def stop_rtp_forward(self, *, stream_id: int):
        return await self.send(SipStopRtpForwardRequest(stream_id=stream_id))

    async def listforwarders(self):
        return await self.send(SipListForwardersRequest())

    async def hangup(self):
        return await self.send(SipHangupRequest())


__all__ = ["SipPlugin"]
