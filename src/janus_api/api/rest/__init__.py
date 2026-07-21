import logging
from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles


from janus_api.conf import settings

logger = logging.getLogger(__name__)

STATICFILES_DIR = getattr(settings, "STATICFILES_DIR")
JANUS_ENABLE_ADMIN = getattr(settings, "JANUS_ENABLE_ADMIN")
ALLOWED_HOSTS = getattr(settings, "ALLOWED_HOSTS")
API_ALLOWED_HEADERS = getattr(settings, "API_ALLOWED_HEADERS", ["*"])
API_ALLOWED_METHODS = getattr(settings, "API_ALLOWED_METHODS", ["GET", "POST"])
API_ALLOW_CREDENTIALS = getattr(settings, "API_ALLOW_CREDENTIALS", True)
MOUNT_LOGGING_APP = getattr(settings, "MOUNT_LOGGING_APP")


def get_rest_api():
    app = FastAPI(title="API Server")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_HOSTS,
        allow_credentials=API_ALLOW_CREDENTIALS,
        allow_methods=API_ALLOWED_METHODS,
        allow_headers=API_ALLOWED_HEADERS,
    )

    from janus_api.api.rest.admin import admin_app
    from janus_api.api.rest.events import events_app
    from janus_api.api.rest.logs import logs_app
    from janus_api.api.rest.manager import manager_app

    app.mount("/static", StaticFiles(directory=STATICFILES_DIR), name="static")
    app.mount("/manager", manager_app, name="manager")
    app.mount("/events", events_app, name="events")

    if MOUNT_LOGGING_APP:
        app.mount("/logs", logs_app, name="logs")
    if JANUS_ENABLE_ADMIN:
        app.mount("/admin", admin_app, name="admin")
    return app
