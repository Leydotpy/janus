from janus_api.plugins.base import PluginBase, PluginRegistry


@PluginRegistry.register(name="audiobridge")
class Audiobridge(PluginBase):

    name = "janus.plugin.audiobridge"

    async def listen(self):
        ...


__all__ = ["Audiobridge"]