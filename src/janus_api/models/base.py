from typing import Literal, Optional
from pydantic import BaseModel


class Jsep(BaseModel):
    type: Literal["offer", "answer"]
    sdp: str
    trickle: Optional[bool]


class PluginMessageBase(BaseModel):
    request: str