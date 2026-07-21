import logging
import json
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


class JsonFormatter(logging.Formatter):
    """
    Emit one JSON object per line (JSON-lines). Minimal but robust:
      - timestamp, logger, level, message
      - optional exc_text for exception tracebacks
      - any extra attributes passed in record.__dict__ under 'extra'
    """
    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None):
        super().__init__(fmt=fmt or "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                         datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:
        data: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "logger": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
        }

        if record.exc_info:
            data["exc_text"] = self.formatException(record.exc_info)
        # include any extras (if user passed extras via logger.bind-style)
        # extras = {
        #     k: v for k, v in record.__dict__.items()
        #     if k not in ("name","msg","args","levelname","levelno","pathname","filename","module",
        #                  "exc_info","exc_text","stack_info","lineno","funcName","created","msecs",
        #                  "relativeCreated","thread","threadName","processName","process","message")
        # }
        #
        #
        # if extras:
        #     data["extra"] = extras

        return json.dumps(data, ensure_ascii=False)