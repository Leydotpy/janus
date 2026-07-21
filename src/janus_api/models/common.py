from __future__ import annotations

from uuid import uuid4

"""Shared helpers used by all Janus plugin model modules.

These models deliberately represent the *plugin-level* JSON body shapes
documented by Janus, rather than the full outer Janus transport envelope.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


HeadersMap = dict[str, str]
StringList = list[str]


class StrictBaseModel(BaseModel):
    """Base class for strictly documented payloads.

    Use this for request/response bodies that are explicitly documented on the
    Janus plugin pages and whose fields should reject unknown properties.
    """

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class LooseBaseModel(BaseModel):
    """Base class for partially documented payloads.

    Some plugin pages list request names or events but do not provide a fully
    expanded JSON schema for them. This base class allows extra keys so the
    model stays practical without pretending the docs were more specific than
    they actually were.
    """

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class JanusJsep(StrictBaseModel):
    """JSEP payload optionally attached to Janus plugin requests or events.

    In Janus, plugin requests that negotiate or renegotiate media may carry a
    `jsep` object in the surrounding Janus message, and asynchronous success
    events may carry a corresponding JSEP answer or update.
    """

    type: Literal["offer", "answer", "pranswer", "rollback"] = Field(
        description="JSEP type such as offer, answer, or pranswer."
    )
    sdp: str = Field(description="Raw SDP content.")
    trickle: bool | None = Field(default=None, description="Optional Janus-side trickle hint.")
    restart: bool | None = Field(default=None, description="Optional ICE-restart hint.")


class PluginErrorResponse(StrictBaseModel):
    """Generic plugin error shape used by several Janus plugins.

    Many Janus plugin pages document errors as a top-level plugin event with an
    `error_code` and human-readable `error` string.
    """

    error_code: int
    error: str


class TransactionalDataMessage(StrictBaseModel):
    """Base class for TextRoom-style DataChannel requests.

    TextRoom DataChannel messages are documented as requiring a `transaction`
    string that is echoed back in the response.
    """

    transaction: str = Field(default_factory=uuid4, description="Client-generated transaction identifier.")
