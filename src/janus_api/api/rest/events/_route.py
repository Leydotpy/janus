import base64
import json
import logging
import secrets
from typing import Optional

from fastapi import FastAPI, Request, Header, HTTPException, status, Depends
from fastapi.security import HTTPBasicCredentials, HTTPBasic
from starlette.middleware.cors import CORSMiddleware

from janus_api.conf import settings

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = getattr(settings, "KAFKA_BOOTSTRAP")
KAFKA_EVENT_HANDLER_TOPIC = getattr(settings, "KAFKA_EVENT_HANDLER_TOPIC")
EVENT_HANDLER_USER = getattr(settings, "EVENT_HANDLER_USER")
EVENT_HANDLER_PASS = getattr(settings, "EVENT_HANDLER_PASS")

app = FastAPI(title="Events API (Push Events)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
)


security = HTTPBasic()


def check_basic_auth(credentials: HTTPBasicCredentials = Depends(security)) -> bool:
    user = secrets.compare_digest(credentials.username, EVENT_HANDLER_USER)
    password = secrets.compare_digest(credentials.password, EVENT_HANDLER_PASS)
    if not (user and password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


@app.post("/janus-events", dependencies=[Depends(check_basic_auth)])
async def janus_events(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    events = payload if isinstance(payload, list) else [payload]

    producer = request.state.producer

    # publish each event to Kafka as a JSON string
    for ev in events:
        try:
            await producer.send_and_wait(KAFKA_EVENT_HANDLER_TOPIC, json.dumps(ev).encode("utf-8"))
        except Exception as e:
            logger.exception("failed to produce event to kafka: %s", e)
            raise HTTPException(status_code=500, detail="failed to enqueue event")

    logger.info("enqueued %d events to kafka topic=%s", len(events), KAFKA_EVENT_HANDLER_TOPIC)
    return {"received": len(events)}
