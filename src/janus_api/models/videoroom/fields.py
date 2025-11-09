import enum
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field, model_validator, ValidationError, field_validator


class AudioCodec(str, Enum):
    opus = enum.auto()
    g722 = enum.auto()
    pcmu = enum.auto()
    pcma = enum.auto()
    isac32 = enum.auto()
    isac16 = enum.auto()


class VideoCodec(str, Enum):
    vp8 = enum.auto()
    vp9 = enum.auto()
    av1 = enum.auto()
    h264 = enum.auto()
    h265 = enum.auto()


class DummyStream(BaseModel):
    codec: VideoCodec = Field(..., description="Video codec to Offer (e.g., vp8, vp9")
    fmtp: Optional[str] = Field(None, description="Optional format parameters to use for the codec")


class Room(BaseModel):
    """
    Represents a room configuration for a janus VideoRoom Instance.
    """
    room: int = Field(..., description="Unique numeric identifier of the room")
    permanent: Optional[bool] = False
    description: Optional[str] = Field(None, description="Room description")
    is_private: Optional[bool] = Field(False, description="Room is private")
    secret: Optional[str] = Field(None, description="Optional Room secret key / password")
    pin: Optional[str] = Field(None, description="Optional Room pin")
    require_pvtid: Optional[bool] = Field(False, description="Room requires PVTID")
    signed_tokens: Optional[bool] = Field(False, description="Room requires signed tokens")
    publishers: int = Field(10, gt=0, description="Max Number of concurrent senders / Publishers")
    bitrate: int = Field(..., gt=0, description="Max bitrate in Kbps")
    bitrate_cap: Optional[bool] = Field(False, description="Max bitrate in Kbps")
    fir_freq: Optional[int] = Field(0, ge=0, description="First frequency to use")

    audiocodec: AudioCodec = Field(..., description="Audio codec to force on publishers (e.g., opus, g722")
    videocodec: VideoCodec = Field(..., description="Video codec to force on publishers (e.g., vp8, vp9")

    vp9_profile: Optional[str] = None
    h264_profile: Optional[str] = None

    opus_fec: Optional[bool] = Field(True)
    opus_dtx: Optional[bool] = Field(False)

    audiolevel_ext: Optional[bool] = Field(True)
    audiolevel_event: Optional[bool] = Field(False)
    audio_active_packets: Optional[int] = Field(100, gt=0)
    audio_level_average: Optional[int] = Field(25, ge=0, le=127)

    videoorient_ext: Optional[bool] = Field(True)
    playoutdelay_ext: Optional[bool] = Field(True)
    transport_wide_cc_ext: Optional[bool] = Field(True)

    record: Optional[bool] = Field(False)
    rec_dir: Optional[str] = Field(None)
    lock_record: Optional[bool] = Field(False)

    notify_joining: Optional[bool] = Field(False)
    require_e2ee: Optional[bool] = Field(False)

    dummy_publisher: Optional[bool] = Field(False)
    dummy_streams: Optional[List[DummyStream]] = None

    threads: Optional[int] = Field(0, ge=0)

    allowed: Optional[List[str]] = Field(None, description="List of string tokens users can use to join the room")

    @model_validator(mode="after")
    def validate_dummy_streams(self, values):
        dummy_publisher = values.get("dummy_publisher")
        dummy_streams = values.get("dummy_streams")
        if dummy_streams and not dummy_publisher:
            raise ValidationError("Dummy streams can only be set if dummy publisher is enabled")
        return values

    @field_validator("rec_dir")
    @classmethod
    def check_recording_dir(cls, v, values):
        if values.get("record") and not v:
            raise ValidationError("Video recording directory must be set if recording is enabled")

    def prepare_model_for_edit(self):
        ...
