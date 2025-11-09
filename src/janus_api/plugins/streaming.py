from janus_api.plugins.base import PluginBase, PluginRegistry


@PluginRegistry.register(name="streaming")
class StreamingPlugin(PluginBase):

    name = "janus.plugin.streaming"