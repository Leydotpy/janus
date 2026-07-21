import logging
from typing import Annotated

from fastapi import FastAPI, Query
from fastapi.requests import Request
from fastapi.middleware.cors import CORSMiddleware

from janus_api.conf import settings
from janus_api.api.rest.manager._helpers import _get_manager_health, check_ready

ALLOWED_HOSTS = getattr(settings, "ALLOWED_HOSTS", [])
API_ALLOWED_HEADERS = getattr(settings, "API_ALLOWED_HEADERS", ["*"])
API_ALLOWED_METHODS = getattr(settings, "API_ALLOWED_METHODS", ["GET", "POST"])
API_ALLOW_CREDENTIALS = getattr(settings, "API_ALLOW_CREDENTIALS", True)

logger = logging.getLogger(__name__)

app = FastAPI(title="Janus Instance Monitoring Server (Readiness + Health)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_HOSTS,
    allow_methods=API_ALLOWED_METHODS,
    allow_headers=API_ALLOWED_HEADERS,
    allow_credentials=API_ALLOW_CREDENTIALS,
) # type: ignore[arg-type]


@app.get("/")
async def manager_health_view(request: Request, room: Annotated[str|None, Query(max_length=20)] = None):
    health = await _get_manager_health(request, room=room)
    return health

@app.get("/ready")
async def manager_ready(request: Request, room: Annotated[str|None, Query(max_length=20)] = None):
    ready = await check_ready(request, room=room)
    return ready
