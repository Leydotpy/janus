import asyncio
import json
import os
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from janus_api.api.rest.logs._helpers import (
    require_api_key,
    verify_api_key,
    offsets_lock,
    offsets,
    subs_lock,
    subscribers,
    _read_record_by_index,
    register_subscriber,
    _remove_subscriber
)
from janus_api.conf import settings

LOG_PATH = getattr(settings, "LOG_PATH")
POLL_INTERVAL = getattr(settings, "POLL_INTERVAL", 0.5)  # seconds to poll for appended data
ALLOWED_HOSTS = getattr(settings, "ALLOWED_HOSTS", [])
API_ALLOWED_HEADERS = getattr(settings, "API_ALLOWED_HEADERS", ["*"])
API_ALLOWED_METHODS = getattr(settings, "API_ALLOWED_METHODS", ["GET", "POST"])
API_ALLOW_CREDENTIALS = getattr(settings, "API_ALLOW_CREDENTIALS", True)

app = FastAPI(title="Log Server (API-key auth + per-conn queues)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_HOSTS,
    allow_methods=API_ALLOWED_METHODS,
    allow_headers=API_ALLOWED_HEADERS,
    allow_credentials=API_ALLOW_CREDENTIALS,
)


###########################
# FastAPI LOGS endpoints       #
###########################
@app.get("/levels", dependencies=[Depends(require_api_key)])
async def get_levels():
    if not os.path.exists(LOG_PATH):
        return {"levels": []}
    levels = set()
    with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh):
            if i > 10000:  # cap to avoid long startup scans
                break
            try:
                obj = json.loads(line)
                lvl = obj.get("level")
                if lvl:
                    levels.add(lvl)
            except Exception:
                continue
    return {"levels": sorted(list(levels))}


@app.get("/", dependencies=[Depends(require_api_key)])
async def get_logs(
        start: int = Query(0, ge=0, description="start index"),
        limit: int = Query(100, ge=1, le=1000, description="number of records"),
        tail: Optional[int] = Query(None, description="return only the last `tail` entries"),
):
    if not os.path.exists(LOG_PATH):
        return JSONResponse({"total": 0, "logs": []})
    async with offsets_lock:
        total = len(offsets)
        if tail:
            if tail <= 0:
                return {"total": total, "count": 0, "logs": []}
            start_idx = max(0, total - tail)
            chosen = list(range(start_idx, total))
        else:
            start_idx = start
            chosen = list(range(start_idx, min(total, start_idx + limit)))
    logs = []
    with open(LOG_PATH, "rb") as fh:
        for idx in chosen:
            fh.seek(offsets[idx])
            raw = fh.readline().decode("utf-8", errors="replace").rstrip("\n")
            try:
                obj = json.loads(raw)
                print(obj)
            except Exception:
                obj = {"raw": raw, "message": raw}
            obj.setdefault("raw", raw)
            logs.append(obj)
    return {"total": total, "count": len(logs), "logs": logs, "start": start if not tail else None}


@app.get("/{idx}", dependencies=[Depends(require_api_key)])
async def get_log(idx: int):
    async with offsets_lock:
        if idx < 0 or idx >= len(offsets):
            raise HTTPException(404, "index out of range")
    rec = _read_record_by_index(idx)
    return rec


###########################
# WebSocket (with API key)#
###########################
@app.websocket("/ws/logs")
async def websocket_logs(ws: WebSocket, last_n: int = 20, api_key: Optional[str] = Query(None)):
    """
    WebSocket endpoint with API-key auth:
      - server checks header 'x-api-key' OR query parameter 'api_key' (query is convenient for browser clients)
      - sends last_n logs, then receives new ones via per-connection queue
    """
    # Extract key from header if provided
    header_key = None
    try:
        header_key = ws.headers.get("X-API-KEY")
    except Exception:
        header_key = None

    key_to_check = header_key or api_key
    if not verify_api_key(key_to_check):
        # reject the websocket: 1008 = policy violation
        await ws.close(code=1008)
        return

    await ws.accept()
    # register subscriber
    sid = await register_subscriber(ws)
    # enqueue last_n logs into the subscriber queue
    async with subs_lock:
        entry = subscribers.get(sid)
        if entry:
            q = entry["queue"]
            # push last_n items (non-blocking, drop oldest on overflow)
            async with offsets_lock:
                total = len(offsets)
                start = max(0, total - last_n)
                chosen = list(range(start, total))
            with open(LOG_PATH, "rb") as fh:
                for idx in chosen:
                    fh.seek(offsets[idx])
                    raw = fh.readline().decode("utf-8", errors="replace").rstrip("\n")
                    try:
                        obj = json.loads(raw)
                    except Exception:
                        obj = {"raw": raw, "message": raw}
                    try:
                        q.put_nowait(obj)
                    except asyncio.QueueFull:
                        try:
                            _ = q.get_nowait()
                        except Exception:
                            pass
                        try:
                            q.put_nowait(obj)
                        except Exception:
                            pass

    # keep connection alive; the _ws_sender_loop sends items from the queue.
    try:
        while True:
            # optionally receive to detect client disconnects or pings
            try:
                await ws.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:
                # ignore other receive errors and sleep a bit
                await asyncio.sleep(POLL_INTERVAL)
    finally:
        # cleanup subscriber (sender task will also remove entry)
        async with subs_lock:
            await _remove_subscriber(sid)


__all__ = ("app",)
