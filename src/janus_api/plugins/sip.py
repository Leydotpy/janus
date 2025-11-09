from janus_api.plugins.base import PluginRegistry, PluginBase


@PluginRegistry.register(name="sip")
class SipPlugin(PluginBase):

    name = 'janus.plugin.sip'