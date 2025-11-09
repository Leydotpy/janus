from janus_api.plugins.base import PluginBase, PluginRegistry


@PluginRegistry.register(name="p2p")
class PeerToPeerPlugin(PluginBase):

    name = "janus.plugin.videocall"

    async def call(self):
        ...

    async def accept(self):
        ...

    async def list(self):
        ...

    async def reject(self):
        ...

    async def set(self):
        ...

    async def register(self):
        ...