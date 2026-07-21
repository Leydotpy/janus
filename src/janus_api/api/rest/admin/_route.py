# main.py
"""
FastAPI application exposing Janus Admin monitor endpoints and a WebSocket streaming route.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, Depends, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import PlainTextResponse
from fastapi.security import APIKeyHeader, HTTPBasicCredentials, HTTPBasic
from pydantic import BaseModel

from janus_api.api.rest.shortcuts import render
from janus_api.conf import settings

logger = logging.getLogger(__name__)

API_KEY = getattr(settings, "JANUS_ADMIN_API_KEY")
JANUS_EVENT_USER = getattr(settings, "EVENT_HANDLER_USER")
JANUS_EVENT_SECRET = getattr(settings, "EVENT_HANDLER_PASS")
ALLOWED_HOSTS = getattr(settings, "ALLOWED_HOSTS")
API_ALLOWED_HEADERS = getattr(settings, "API_ALLOWED_HEADERS", ["*"])
API_ALLOWED_METHODS = getattr(settings, "API_ALLOWED_METHODS", ["GET", "POST"])
API_ALLOW_CREDENTIALS = getattr(settings, "API_ALLOW_CREDENTIALS", True)

security = HTTPBasic()
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)


async def require_api_key(api_key: str = Depends(api_key_header)):
    """
    Simple API key dependency. In production swap to OAuth/JWT as needed.
    """
    if not api_key or api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


async def verify_event_secret(credentials: HTTPBasicCredentials = Depends(security)) -> bool:
    user_ok = secrets.compare_digest(credentials.username, JANUS_EVENT_USER)
    pass_ok = secrets.compare_digest(credentials.password, JANUS_EVENT_SECRET)

    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid event credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


app = FastAPI(title="Janus Admin Monitor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_HOSTS,  # Vite default
    allow_credentials=API_ALLOW_CREDENTIALS,
    allow_methods=API_ALLOWED_METHODS,
    allow_headers=API_ALLOWED_HEADERS,
)


# REST endpoints ---------------------------------------------------------------

@app.get("/", dependencies=[Depends(require_api_key)])
async def get_root(request: Request):
    return render(
        request,
        "admin/index.html",
        {}
    )


@app.get("/info", dependencies=[Depends(require_api_key)])
async def get_info(request: Request):
    monitor = request.state.monitor
    try:
        info = await monitor.info()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    data = {"info": info}
    return JSONResponse(content=data, media_type="application/json")


@app.get("/sessions")
async def get_sessions(request: Request):
    monitor = request.state.monitor
    try:
        sessions = await monitor.list_sessions()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"sessions": sessions}


@app.get("/session/{session_id}/handles")
async def get_handles(request: Request, session_id: int):
    monitor = request.state.monitor
    try:
        handles = await monitor.list_handles(session_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"session_id": session_id, "handles": handles}


@app.get("/session/{session_id}/handle/{handle_id}")
async def get_handle_info(request: Request, session_id: int, handle_id: int,
                          plugin_only: Optional[bool] = False):
    monitor = request.state.monitor
    try:
        info = await monitor.handle_info(session_id, handle_id, plugin_only=plugin_only)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return info


# Add POST endpoint for Janus EventHandler push

# Aggregation endpoint example: per-room average of metric
@app.get("/aggregates/{group_by}")
async def aggregates(request: Request, group_by: str, start: str, stop: str, metric_key: str,
                     time_bucket: str = "1 minute",
                     plugin: str = None):
    if group_by not in ("plugin", "room_id", "peer_id", "handle_id"):
        raise HTTPException(status_code=400, detail="invalid group_by")
    storage = request.state.storage
    rows = await storage.query_aggregate(start, stop, group_by, metric_key, plugin=plugin, time_bucket=time_bucket)
    return {"group_by": group_by, "metric_key": metric_key, "rows": rows}


# WebSocket endpoint for real-time streaming of events/metrics -----------------

@app.websocket("/ws/monitor")
async def websocket_monitor(ws: WebSocket):
    await ws.accept()
    monitor = ws.state.monitor
    q = monitor.subscribe()
    try:
        # Immediately send a welcome + current sessions snapshot
        try:
            info = await monitor.info()
        except Exception:
            info = {"error": "could not fetch info"}

        await ws.send_json({"type": "welcome", "info": info})
        # start sending broadcast events produced by monitor
        while True:
            payload = await q.get()
            # Forward to client
            await ws.send_json(payload)
    except WebSocketDisconnect:
        monitor.unsubscribe(q)
    except Exception:
        monitor.unsubscribe(q)
        try:
            await ws.close()
        except Exception:
            pass


@app.post("/event", dependencies=[Depends(verify_event_secret)])
async def janus_event(req: Request):
    payload = await req.json()
    monitor = req.state.monitor
    # handle_eventhandler_payload does broadcasting + optionally persistence
    await monitor.handle_event_handler_payload(payload)
    return {"ok": True}


@app.get("/metrics")
async def prometheus_metrics(request: Request, ):
    """
    Simple Prometheus exposition: for each room, expose current 1-min avg inbound/outbound bitrate and sum packets_lost.
    Scrape range: last 5 minutes aggregated by 1 minute buckets; we return the latest bucket per room.
    """
    storage = request.state.storage
    stop = datetime.now(timezone.utc)
    start = stop - timedelta(minutes=5)
    # TimescaleStorage.query_aggregate expects ISO strings for start/stop
    rows = await storage.query_aggregate(start.isoformat(), stop.isoformat(), group_by="room_id",
                                         metric_key="inbound_bytes", time_bucket="1 minute")
    # rows is list of {bucket,label,avg,sum,max}
    lines = ["# HELP janus_inbound_bytes_avg_avg 1m average inbound_bytes per room",
             "# TYPE janus_inbound_bytes_avg_avg gauge"]
    # HELP / TYPE lines
    # choose latest per room
    latest_per_room = {}
    for r in rows:
        label = r["label"] or "unknown"
        # store last bucket seen (rows ordered by bucket asc from query_aggregate)
        latest_per_room[label] = r

    for room, r in latest_per_room.items():
        metric_name = "janus_inbound_bytes_avg"
        val = r["avg"] or 0
        # labels: room
        lines.append(f'{metric_name}{{room="{room}"}} {val}')

    # Similar blocks can be added for outbound_bytes and packets_lost by calling query_aggregate with those metric_key values
    body = "\n".join(lines) + "\n"
    return PlainTextResponse(body, media_type="text/plain; version=0.0.4")


class TimeSeriesQuery(BaseModel):
    metric_key: Optional[str] = None


@app.get("/metrics/session/{session_id}/handle/{handle_id}")
async def get_metrics(request: Request, session_id: int, handle_id: int, metric_key: Optional[str] = None):
    monitor = request.state.monitor
    ts = monitor.get_timeseries(session_id, handle_id, metric_key)
    return {"session_id": session_id, "handle_id": handle_id, "timeseries": ts}
