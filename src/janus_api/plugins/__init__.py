from janus_api.plugins.base import Plugin, PluginRegistry

def _load_plugins():
    try:
        PluginRegistry.load()
    except Exception as err:
        raise err


_load_plugins()

__all__ = ["Plugin"]