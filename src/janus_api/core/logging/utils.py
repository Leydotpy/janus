import logging
import sys
from typing import Any, Dict, Optional

from janus_api.core.logging._json import JsonFormatter

from janus_api.core.logging.formatting import ColoredFormatter, DEFAULT_LEVEL_STYLES, RESET


def get_colored_stream_handler(
    level: int = logging.DEBUG,
    fmt: Optional[str] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt: Optional[str] = "%Y-%m-%d %H:%M:%S",
    level_styles: Optional[dict] = None,
    use_color: bool = True,
) -> logging.StreamHandler:
    """
    Create a StreamHandler with the ColoredFormatter attached.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    formatter = ColoredFormatter(fmt=fmt, datefmt=datefmt, level_styles=level_styles, use_color=use_color)
    handler.setFormatter(formatter)
    return handler


def get_json_file_handler(
    path: str,
    level: int = logging.DEBUG,
    datefmt: Optional[str] = "%Y-%m-%d %H:%M:%S",
) -> logging.FileHandler:
    fh = logging.FileHandler(path, mode="a", encoding="utf-8")
    fh.setLevel(level)
    formatter = JsonFormatter(datefmt=datefmt)
    fh.setFormatter(formatter)
    return fh


def get_plain_file_handler(
    path: str,
    level: int = logging.DEBUG,
    fmt: Optional[str] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt: Optional[str] = "%Y-%m-%d %H:%M:%S",
) -> logging.FileHandler:
    """
    File handler that writes plain (ANSI-stripped) logs to disk.
    """
    fh = logging.FileHandler(path)
    fh.setLevel(level)
    formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)
    fh.setFormatter(formatter)
    return fh


def install_colored_logging(
    *,
    level: int = logging.DEBUG,
    root_logger: Optional[logging.Logger] = None,
    keep_existing_handlers: bool = False,
    color_stdout: bool = True,
    logfile: Optional[str] = None,
) -> logging.Logger:
    if root_logger is None:
        root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if not keep_existing_handlers:
        for h in list(root_logger.handlers):
            root_logger.removeHandler(h)

    # Stream handler (colored)
    stream_h = get_colored_stream_handler(level=level, use_color=color_stdout)
    root_logger.addHandler(stream_h)

    # JSON file handler (one JSON object per line)
    if logfile:
        fh = get_json_file_handler(logfile, level=level)
        root_logger.addHandler(fh)

    return root_logger


if __name__ == "__main__":
    import logging
    from janus_api.conf import settings

    LOG_FILE_DIR = getattr(settings, "LOG_FILE_DIR", None)

    if not LOG_FILE_DIR:
        raise FileNotFoundError("LOG_FILE_DIR not set")

    install_colored_logging(level=logging.DEBUG, logfile=LOG_FILE_DIR)

    log = logging.getLogger("demo")
    log.debug("debugging details here")
    log.info("regular info")
    log.warning("something odd happened")
    try:
        1/0
    except Exception as e:
        log.exception("caught an exception", exc_info=e)
    log.critical("critical failure")