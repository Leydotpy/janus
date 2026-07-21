from typing import Mapping, Optional

from pydantic import BaseModel


class ManagerHealth(BaseModel):
    service: str
    attached: bool
    plugin_id: Optional[str]
    attached_since: Optional[float]
    sample_room_check: Optional[Mapping[str, str|bool] | Mapping[str, bool]]


class ManagerReady(BaseModel):
    ready: bool
    detail: str
    error: Optional[str] = None
