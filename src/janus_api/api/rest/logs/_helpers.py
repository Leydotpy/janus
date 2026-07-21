import asyncio
import json
import os
import secrets
import uuid
from typing import Dict, List, Optional

from fastapi import WebSocket, HTTPException, status, Depends
from fastapi.security import APIKeyHeader

from janus_api.conf import settings

LOG_PATH = getattr(settings, "LOG_PATH")
POLL_INTERVAL = getattr(settings, "POLL_INTERVAL", 0.5)  # seconds to poll for appended data
WS_QUEUE_MAXSIZE = getattr(settings, "WS_QUEUE_MAXSIZE", 1000)  # per-connection queue size

# API key (change via env in production)
API_KEY = getattr(settings, "LOG_VIEW_API_KEY", "dev-key")

# In-memory offsets index
offsets: List[int] = []
offsets_lock = asyncio.Lock()

# subscribers: mapping id -> dict with 'ws', 'queue', 'task'
subscribers: Dict[str, Dict] = {}
subs_lock = asyncio.Lock()  # guard subscribers dict

api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)


###########################
# Authentication helpers  #
###########################
def verify_api_key(key: Optional[str] = "dev-key") -> bool:
    """Constant-time compare of API keys."""
    if not key:
        return False
    return secrets.compare_digest(key, API_KEY)


async def require_api_key(x_api_key: Optional[str] = Depends(api_key_header)):
    """
    Dependency for HTTP endpoints.
    Looks for the key in header 'x-api-key'.
    """
    if not verify_api_key(x_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "API key"},
        )
    return x_api_key


###########################
# Indexing + tailing      #
###########################
async def build_index():
    """(Re)build the offsets index by scanning the file once."""
    global offsets
    offsets_local: List[int] = []
    if not os.path.exists(LOG_PATH):
        offsets = []
        return
    with open(LOG_PATH, "rb") as fh:
        pos = fh.tell()
        line = fh.readline()
        while line:
            offsets_local.append(pos)
            pos = fh.tell()
            line = fh.readline()
    async with offsets_lock:
        offsets = offsets_local


async def publish_to_subscribers(obj: Dict):
    """
    Non-blocking publish to all subscriber queues.
    If a subscriber queue is full, drop the oldest item to make room.
    """
    async with subs_lock:
        dead = []
        for sid, entry in list(subscribers.items()):
            q: asyncio.Queue = entry["queue"]
            try:
                q.put_nowait(obj)
            except asyncio.QueueFull:
                # drop oldest to make room
                try:
                    _ = q.get_nowait()
                except Exception:
                    pass
                try:
                    q.put_nowait(obj)
                except Exception:
                    dead.append(sid)
        # cleanup dead subscribers
        for sid in dead:
            await _remove_subscriber(sid)


async def tail_file_and_broadcast():
    """Background task: open the file, read appended lines and publish them."""
    await build_index()
    last_known_offset = offsets[-1] + 1 if offsets else 0
    while True:
        if not os.path.exists(LOG_PATH):
            await asyncio.sleep(POLL_INTERVAL)
            continue
        try:
            with open(LOG_PATH, "rb") as fh:
                fh.seek(0, os.SEEK_END)
                file_end = fh.tell()
                # file truncated => rebuild index
                if file_end < last_known_offset:
                    await build_index()
                    last_known_offset = offsets[-1] + 1 if offsets else 0
                fh.seek(last_known_offset)
                while True:
                    pos = fh.tell()
                    line = fh.readline()
                    if not line:
                        break
                    # record offset
                    async with offsets_lock:
                        offsets.append(pos)
                    last_known_offset = fh.tell()
                    text = line.decode("utf-8", errors="replace").rstrip("\n")
                    try:
                        obj = json.loads(text)
                    except Exception:
                        obj = {"raw": text, "message": text}
                    await publish_to_subscribers(obj)
        except Exception:
            # resilient: swallow errors and retry
            pass
        await asyncio.sleep(POLL_INTERVAL)


###########################
# Subscriber management   #
###########################
async def _remove_subscriber(sid: str):
    """Cleanup a subscriber (cancel task, remove queue entry)."""
    entry = subscribers.get(sid)
    if not entry:
        return
    task = entry.get("task")
    try:
        if task:
            task.cancel()
    except Exception:
        pass
    try:
        del subscribers[sid]
    except KeyError:
        pass


async def _ws_sender_loop(sid: str, ws: WebSocket, queue: asyncio.Queue):
    """
    Per-connection sender loop. Reads from the queue and sends to websocket.
    Stops when send fails or websocket is closed.
    """
    try:
        while True:
            item = await queue.get()  # awaitable; won't block the tailer
            try:
                await ws.send_text(json.dumps(item, ensure_ascii=False))
            except Exception:
                break
    finally:
        # cleanup on exit
        await _remove_subscriber(sid)
        try:
            await ws.close()
        except Exception:
            pass


async def register_subscriber(ws: WebSocket) -> str:
    """Create a new subscriber entry and start its sender task."""
    sid = str(uuid.uuid4())
    q: asyncio.Queue = asyncio.Queue(maxsize=WS_QUEUE_MAXSIZE)
    task = asyncio.create_task(_ws_sender_loop(sid, ws, q))
    async with subs_lock:
        subscribers[sid] = {"ws": ws, "queue": q, "task": task}
    return sid


###########################
# Helpers to read records #
###########################
def _read_record_by_index(idx: int) -> Dict:
    if not os.path.exists(LOG_PATH):
        raise IndexError("log file missing")
    with open(LOG_PATH, "rb") as fh:
        with_offsets = offsets
        if idx < 0 or idx >= len(with_offsets):
            raise IndexError("index out of range")
        fh.seek(with_offsets[idx])
        raw = fh.readline().decode("utf-8", errors="replace").rstrip("\n")
        try:
            obj = json.loads(raw)
        except Exception:
            obj = {"raw": raw, "message": raw}
        obj.setdefault("raw", raw)
        return obj
