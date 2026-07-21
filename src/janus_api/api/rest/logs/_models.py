from typing import Optional

from pydantic import BaseModel


class LogRecord(BaseModel):
    timestamp: Optional[str] = None
    logger: Optional[str] = None
    level: Optional[str] = None
    message: Optional[str] = None
    exc_text: Optional[str] = None
    extra: Optional[dict] = None
    raw: Optional[str] = None
