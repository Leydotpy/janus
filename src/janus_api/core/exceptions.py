# ----------------------
# Exceptions
# ----------------------

class JanusException(Exception):
    """Base exception for Janus."""


class PluginManagerError(JanusException):
    """Base exception for the plugin manager."""


class PluginAlreadyRegistered(PluginManagerError):
    """Raised when attempting to register a plugin under a plugin_id that's already used."""


class PluginNotRegistered(PluginManagerError, KeyError):
    """Raised when attempting to access or remove a plugin that isn't registered."""


class JanusTransportError(JanusException):
    """Base exception for JanusTransport."""
    def __init__(self, code, reason):
        self._error_code = code
        self._reason = reason
        super().__init__(f"JanusTransportError: {code} - {reason}")