from pydantic import BaseModel, ConfigDict, Field

from janus_api.models.common import JanusJsep, StrictBaseModel


class Jsep(JanusJsep):
    """Backward-compatible alias for Janus JSEP payloads."""


class PluginMessageBase(StrictBaseModel):
    request: str


def _base_config(*, extra: str = "forbid") -> ConfigDict:
    return ConfigDict(
        extra=extra,
        str_strip_whitespace=True,
        populate_by_name=True,
        validate_assignment=True,
    )


class PluginResponseBase(BaseModel):
    model_config = _base_config(extra="ignore")

    # Internal discriminator used by our wrappers only.
    kind: str = Field(default="", exclude=True)
