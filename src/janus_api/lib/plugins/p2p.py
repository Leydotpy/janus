from janus_api.lib.plugins.base import Plugin


class PeerToPeerPlugin(Plugin):

    name = "janus.plugin.videocall"
    identifier = "peer_to_peer"


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

__all__ = ["PeerToPeerPlugin"]