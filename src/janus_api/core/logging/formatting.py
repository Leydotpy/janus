"""
colored_logging.py
Simple, flexible colored logging that plugs into Python's logging module.

Usage:
    from colored_logging import install_colored_logging, get_colored_stream_handler

    # Simple global setup:
    install_colored_logging(level=logging.DEBUG)

    logging.getLogger(__name__).info("hello world")
"""

from __future__ import annotations
import logging
import sys
import re
from typing import Dict, Optional

# Try to import colorama for Windows support; fall back silently if missing.
try:
    import colorama  # type: ignore
    _HAS_COLORAMA = True
except Exception:
    _HAS_COLORAMA = False

# ANSI escape helpers
CSI = "\x1b["
RESET = CSI + "0m"

# Basic styles
STYLE_BOLD = CSI + "1m"
STYLE_DIM = CSI + "2m"

# Foreground colors
FG_BLACK   = CSI + "30m"
FG_RED     = CSI + "31m"
FG_GREEN   = CSI + "32m"
FG_YELLOW  = CSI + "33m"
FG_BLUE    = CSI + "34m"
FG_MAGENTA = CSI + "35m"
FG_CYAN    = CSI + "36m"
FG_WHITE   = CSI + "37m"

# Bright foregrounds
FG_BRIGHT_BLACK   = CSI + "90m"
FG_BRIGHT_RED     = CSI + "91m"
FG_BRIGHT_GREEN   = CSI + "92m"
FG_BRIGHT_YELLOW  = CSI + "93m"
FG_BRIGHT_BLUE    = CSI + "94m"
FG_BRIGHT_MAGENTA = CSI + "95m"
FG_BRIGHT_CYAN    = CSI + "96m"
FG_BRIGHT_WHITE   = CSI + "97m"


DEFAULT_LEVEL_STYLES: Dict[int, str] = {
    logging.DEBUG: FG_BRIGHT_CYAN,               # debug = cyan
    logging.INFO: FG_BRIGHT_GREEN,               # info = green
    logging.WARNING: FG_BRIGHT_YELLOW + STYLE_BOLD,  # warning = bold yellow
    logging.ERROR: FG_BRIGHT_RED + STYLE_BOLD,    # error = bold red
    logging.CRITICAL: FG_BRIGHT_RED + STYLE_BOLD + CSI + "5m",  # blink + bold red (may not show everywhere)
}

# Which parts we color by default
DEFAULT_COLOR_TARGETS = ("levelname", "message", "name", "asctime")  # could be ('levelname', ) etc.


class ColoredFormatter(logging.Formatter):
    """
    Logging Formatter that injects ANSI color escape sequences based on record.levelno.

    Options:
      - fmt / datefmt / style: same as logging.Formatter
      - level_styles: dict mapping logging levels to ANSI prefix strings
      - use_color: bool — whether to emit ANSI escapes
      - color_targets: tuple of record attributes to color ('levelname', 'message', ...)
    """

    _ansi_strip_re = re.compile(r"\x1b\[[0-9;]*m")

    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
        style: str = "%",
        level_styles: Optional[Dict[int, str]] = None,
        use_color: bool = True,
        color_targets: tuple = DEFAULT_COLOR_TARGETS,
    ) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt, style=style)
        self.level_styles = level_styles or DEFAULT_LEVEL_STYLES
        self.use_color = use_color
        self.color_targets = color_targets

    @staticmethod
    def _colorize(text: str, color_prefix: str, use_color: bool) -> str:
        if not use_color or not color_prefix:
            return text
        return f"{color_prefix}{text}{RESET}"

    def format(self, record: logging.LogRecord) -> str:
        # Optionally initialize colorama for Windows (only if we need color)
        if self.use_color and _HAS_COLORAMA:
            # safe to call multiple times
            colorama.init()

        # get the style for the current level
        color_prefix = self.level_styles.get(record.levelno, "")

        # We'll format the message using the parent's logic but with colored fields.
        # Make a shallow copy of attributes we may mutate so we don't mutate the original record.
        record_copy = logging.makeLogRecord(record.__dict__.copy())

        # Color levelname and/or message depending on configuration
        # if "asctime" in self.color_targets:
        #     record_copy.asctime = self._colorize(record_copy.asctime, color_prefix, self.use_color)

        if "name" in self.color_targets:
            record_copy.name = self._colorize(record_copy.name, color_prefix, self.use_color)

        if "levelname" in self.color_targets:
            record_copy.levelname = self._colorize(record.levelname, color_prefix, self.use_color)

        if "message" in self.color_targets:
            # logging.Formatter.format() calls self.formatMessage(record) which uses %(message)s.
            # We can pre-color the message string itself so that when it's interpolated it appears colored.
            # But the record may not have a formatted message yet; compute record.getMessage().
            try:
                original_message = record.getMessage()
            except Exception:
                # fallback if formatting of message throws
                original_message = str(record.msg)
            record_copy.msg = self._colorize(original_message, color_prefix, self.use_color)
            record_copy.args = ()  # message already formatted

        # Use the parent class to produce the formatted text
        formatted = super().format(record_copy)

        # If an exception / traceback is present, logging.Formatter.format will have appended it.
        # Color the traceback lines too (we'll apply same color for readability)
        if record.exc_info or record.exc_text:
            # The parent format already appended exception text; color any ANSI-less trace
            if self.use_color:
                formatted = self._colorize(formatted, color_prefix, True)
        return formatted

    @classmethod
    def strip_ansi(cls, s: str) -> str:
        """Remove ANSI escapes (useful when writing to files)."""
        return cls._ansi_strip_re.sub("", s)