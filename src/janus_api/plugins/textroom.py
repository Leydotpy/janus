from .base import PluginBase, PluginRegistry


@PluginRegistry.register(name="textroom")
class TextRoomPlugin(PluginBase):

    name = "janus.plugin.textroom"

    async def create(self):
        ...

    async def list(self):
        ...


__all__ = ["TextRoomPlugin"]