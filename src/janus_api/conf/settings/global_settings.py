from pathlib import Path

from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DEBUG = True

SECRET_KEY = config("SECRET_KEY", default='django-insecure-*gv!%-w336n_kfq15ktybni2nthx+4tyobekl4xvgf4^%*6$fz', cast=str)


REDIS_URL = config("REDIS_URL", "redis://localhost:6379/0")
LEADER_LOCK_KEY = config("LEADER_LOCK_KEY", "janus:leader")
LEADER_LOCK_TTL = config("LEADER_LOCK_TTL", cast=int, default=10)
LEADER_REFRESH_INTERVAL = config("LEADER_REFRESH_INTERVAL", cast=int, default=5)
JANUS_SESSION_URL = config("JANUS_SESSION_URL", "ws://localhost:8188/janus")
LEADER_MODE = config("LEADER_MODE", default=1, cast=bool)
LEADER_PROXY_HOST = config("JANUS_SESSION_LEADER_PROXY_HOST", default="127.0.0.1")
LEADER_PROXY_PORT = config("JANUS_SESSION_LEADER_PROXY_PORT", default="5901", cast=int)
ALLOWED_PROXY_METHODS = ["create", "destroy", "attach", "keepalive", "plugin_request"]
# monitor backoff for re-create attempts
MONITOR_BACKOFF = config("MONITOR_BACKOFF", cast=int, default=5)

LOG_FILE_DIR = BASE_DIR / "logs" / "app.log"

MOUNT_LOGGING_APP = config("MOUNT_LOGGING_APP", cast=bool, default=1)
MOUNT_REST_API = config("MOUNT_REST_API", cast=bool, default=1)

LOG_PATH = LOG_FILE_DIR
POLL_INTERVAL = config("POLL_INTERVAL", cast=float, default=0.5)  # seconds to poll for appended data
WS_QUEUE_MAXSIZE = config("WS_QUEUE_MAXSIZE", cast=int, default=1000)  # per-connection queue size

# API key (change via env in production)
LOG_VIEW_API_KEY = config("LOG_VIEW_API_KEY", default=SECRET_KEY, cast=str)

TEMPLATE = {
    "BACKEND": "fastapi.templating.Jinja2Templates",
    "DIR": BASE_DIR / "templates",
    "OPTIONS": {
        "context_processors": [
            "janus_api.api.rest.context_processors.debug_processor",
            "janus_api.api.rest.context_processors.common_context",
        ],
        # set to False to force processors to run every render (no caching)
        "cache_context_processors": True,
    },
}


STATICFILES_DIR = BASE_DIR / "static"

ALLOWED_HOSTS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8000",
]

API_ALLOW_CREDENTIALS = True
API_ALLOWED_METHODS = [
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
    "HEAD",
    "TRACE",
]
API_ALLOWED_HEADERS = ["*"]

JANUS_ENABLE_ADMIN = config("JANUS_ENABLE_ADMIN", cast=bool, default=1)
JANUS_ADMIN_CACHE_DIR = config("cache_dir", cast=str, default=BASE_DIR / "cache")
JANUS_ROOM_CACHE_TTL = config("JANUS_ROOM_CACHE_TTL", default=30, cast=int)
JANUS_ADMIN_URL = config("JANUS_ADMIN_URL", default="http://localhost:7088/admin", cast=str)
JANUS_ADMIN_WS_URL = config("JANUS_ADMIN_WS_URL", cast=str, default="ws://127.0.0.1:7188/admin")  # replace with your janus admin ws
JANUS_ADMIN_SECRET = config("JANUS_ADMIN_SECRET", default=SECRET_KEY, cast=str)  # set to your admin_secret if configured
JANUS_ADMIN_API_KEY = config("JANUS_ADMIN_API_KEY", cast=str, default=SECRET_KEY)

# TIMESCALE PG CONFIG
TIMESCALE_PG_USER = config("TIMESCALE_PG_USER", default="postgres", cast=str)
TIMESCALE_PG_PASS = config("TIMESCALE_PG_PASS", default="L_akanbi1996", cast=str)
TIMESCALE_PG_HOST = config("TIMESCALE_PG_HOST", default="localhost", cast=str)
TIMESCALE_PG_PORT = config("TIMESCALE_PG_PORT", default="5432", cast=str)
TIMESCALE_PG_NAME = config("TIMESCALE_PG_NAME", default="janus_metrics", cast=str)
TIMESCALE_DSN = f"postgres://{TIMESCALE_PG_USER}:{TIMESCALE_PG_PASS}@{TIMESCALE_PG_HOST}:{TIMESCALE_PG_PORT}/{TIMESCALE_PG_NAME}"

JANUS_ENABLE_EVENTS = config("JANUS_ENABLE_EVENTS", cast=bool, default=0)
KAFKA_BOOTSTRAP = config("KAFKA_BOOTSTRAP", default="kafka:9092", cast=str)
KAFKA_EVENT_HANDLER_TOPIC = config("KAFKA_EVENT_HANDLER_TOPIC", default="janus.events", cast=str)
EVENT_HANDLER_USER = config("EVENT_HANDLER_USER", default="janus", cast=str)
EVENT_HANDLER_PASS = config("EVENT_HANDLER_PASS", default=SECRET_KEY, cast=str)