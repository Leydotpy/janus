from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional, Sequence, Union

from starlette.applications import Starlette
from starlette.routing import Mount  # keep Route import for type hinting

from janus_api.conf import settings
from janus_api.core import install_colored_logging

Logger = logging.getLogger(__name__)

# Allowed kwargs to pass to starlette.routing.Mount
_ALLOWED_MOUNT_KWARGS = {"path", "app", "name", "include_in_schema"}

MOUNT_REST_API = getattr(settings, "MOUNT_REST_API")
LOG_FILE_DIR = getattr(settings, "LOG_FILE_DIR", None)

ASGIApp = Any  # more precise: Callable[[scope], Awaitable] but keep Any for simplicity
RouteSpec = Union[Mapping[str, Any], Mount]


def _is_asgi_callable(obj: Any) -> bool:
    """Rudimentary ASGI app check: callable or has '__call__'."""
    return callable(obj) or hasattr(obj, "__call__")


def _build_mount_from_spec(spec: RouteSpec) -> Mount:
    """
    Build a starlette.routing.Mount from a mapping or return the Mount unchanged.

    - If `spec` is already a Mount, return it.
    - If `spec` is a Mapping, validate required keys and construct Mount(**kwargs).
    """
    if isinstance(spec, Mount):
        return spec

    if not isinstance(spec, Mapping):
        raise TypeError("route spec must be a starlette.routing.Mount or a mapping")

    # Ensure required fields
    if "path" not in spec:
        raise ValueError("route spec mapping is missing required key 'path'")
    if "app" not in spec:
        raise ValueError("route spec mapping is missing required key 'app'")

    path = spec["path"]
    app = spec["app"]

    if not isinstance(path, str):
        raise TypeError("route spec 'path' must be a string")
    if not _is_asgi_callable(app):
        raise TypeError("route spec 'app' must be an ASGI app or callable")

    # Filter allowed kwargs and preserve extras only if they match allowed set
    kwargs: MutableMapping[str, Any] = {
        k: spec[k] for k in spec.keys() if k in _ALLOWED_MOUNT_KWARGS
    }

    # Make sure we pass path and app explicitly (positional style is fine)
    try:
        return Mount(**kwargs)  # type: ignore[arg-type]
    except TypeError as exc:
        # wrap with clearer diagnostics
        raise ValueError(
            "failed to construct starlette.routing.Mount from spec; "
            f"allowed keys: {_ALLOWED_MOUNT_KWARGS}. original error: {exc}"
        ) from exc


def ensure_log_file(
    logfile: str | Path | None,
    *,
    default_logfile: str | Path | None = None,
    logger=None,
) -> Path | None:
    """
    Resolve and ensure the log file exists.

    Behaviour:
    - Uses `logfile` if provided, otherwise falls back to `default_logfile`.
    - Creates parent directories if they do not exist.
    - Creates the file if it does not exist.
    - Returns the resolved Path, or None if no log file is configured.
    """
    raw_path = logfile or default_logfile
    if not raw_path:
        return None

    path = Path(raw_path).expanduser()

    try:
        parent = path.parent
        if not parent.exists():
            if logger:
                logger.info("Creating log directory: %s", parent)
            parent.mkdir(parents=True, exist_ok=True)

        if not path.exists():
            if logger:
                logger.info("Creating log file: %s", path)
            path.touch(exist_ok=True)

        if not path.is_file():
            raise ValueError(f"Expected a file path, got non-file path: {path}")

        return path

    except Exception:
        if logger:
            logger.exception("Failed to prepare log file path: %s", path)
        raise

def create_asgi_app(
    *,
    debug: bool = False,
    routes: Optional[Sequence[RouteSpec]] = None,
    mount_rest_api: bool = True,
    initialize_logging: bool = True,
    logfile: Optional[str] = None,
) -> Starlette:
    """
    Construct and return a Starlette application from a sequence of route specs.

    Args:
        debug: Starlette debug mode.
        routes: Sequence of mappings (with keys 'path' and 'app') or Mount instances.
        mount_rest_api: If True, mounts the logging UI at '/logs' (expects `janus_api.servers.logs.app`).
        initialize_logging: If True, call install_colored_logging() before creating app.
        logfile: path to logfile passed to install_colored_logging (overrides settings.LOG_FILE_DIR).

    Returns:
        Starlette instance.

    Example:
        >>> from janus_api.servers.asgi import create_asgi_app

        >>> # route specs can be mapping or Mount objects
        >>> routes = [
        >>>    {"path": "/api", "app": my_api_asgi_app},
        >>>    {"path": "/static", "app": static_asgi_app, "include_in_schema": False},
        >>> ]

        >>> app = create_asgi_app(debug=False, routes=routes, mount_rest_api=True, initialize_logging=True)
    """
    if initialize_logging:
        logfile_to_use = ensure_log_file(
            logfile=logfile,
            default_logfile=LOG_FILE_DIR,
            logger=Logger
        )
        install_colored_logging(level=logging.DEBUG, logfile=str(logfile_to_use))

    if routes is None:
        routes_list: Sequence[RouteSpec] = []
    else:
        routes_list = routes

    built_routes: list[Mount] = []
    for idx, r in enumerate(routes_list):
        try:
            built_routes.append(_build_mount_from_spec(r))
        except Exception as exc:
            Logger.error("invalid route at index %d: %r -> %s", idx, r, exc)
            raise

    if mount_rest_api:
        Logger.info("mounting rest api apps")
        # lazy import so consumers who don't want the logging server don't import it at module import time
        try:
            from janus_api.api import get_rest_api # local import
        except Exception as exc:
            Logger.exception("failed to import logging app for mount at '/logs'", exc_info=exc)
            raise

        built_routes.append(_build_mount_from_spec({"path": "/janus", "app": get_rest_api()}))
    else:
        Logger.info(f"rest api not mounted because mount_internal_rest_api is set to {mount_rest_api}")
    # lifespan hooks
    try:
        from janus_api.servers.asgi._hooks import lifespan  # local import
    except Exception as e:
        Logger.exception("failed to import lifespan hook for Starlette application", exc_info=e)
        lifespan = None

    return Starlette(debug=debug, routes=built_routes, lifespan=lifespan)
