# Janus Core

Production-oriented, async Python foundations for the
[Janus WebRTC Gateway](https://janus.conf.meetecho.com/): sessions, transports,
authentication, protocol envelopes, plugin-handle lifecycle, event routing, and
an optional operations API.

Janus Core intentionally contains **no named Janus plugin implementation**.
EchoTest, VideoCall, SIP, NoSIP, AudioBridge, VideoRoom, TextRoom, and
Record&Play are independent projects in `plugins/`; Streaming lives entirely
in `plugins/janus-streaming-plugin`. Applications can install only what
they use or implement their own client on the public `Plugin` base.

> The product is named **Janus Core**. The exact `janus-core` distribution and
> `janus_core` import namespace are already occupied on PyPI by an unrelated
> project, so this project uses the publishable distribution name
> `janus-api-core` and retains the stable `janus_api` Python namespace.

## Requirements and installation

- Python 3.11+
- Janus Gateway with at least one enabled API transport

```bash
pip install janus-api-core

# Plain HTTP/HTTPS transport
pip install "janus-api-core[http]"

# FastAPI operations service, Admin/Monitor, Kafka, and Timescale support
pip install "janus-api-core[ops,server]"
```

The base installation contains only Pydantic, RxPY, and WebSockets. Database,
Kafka, HTTP-client, ASGI, and server dependencies are opt-in.

## Client quick start

Install only the named plugin an application needs:

```bash
pip install janus-echotest-plugin
```

```python
import asyncio

from janus_api import JanusSession
from janus_echotest_plugin import EchoTestPlugin


async def main() -> None:
    async with JanusSession(url="ws://127.0.0.1:8188/janus") as session:
        async with EchoTestPlugin(session=session) as echo:
            reply = await echo.configure(audio=True, video=False)
            print(reply.data)


asyncio.run(main())
```

Use the same session API with Janus REST; long polling and REST path addressing
are managed by the HTTP transport:

```python
async with JanusSession(url="http://127.0.0.1:8088/janus") as session:
    ...
```

WebSocket disconnects invalidate every session and handle bound to that socket.
The manager creates fresh sessions rather than silently reusing stale Janus IDs.
Requests have bounded transaction tables and explicit timeouts; cancellation
always releases the pending transaction. Shutdown detaches handles with bounded
concurrency, reserves time for the Janus session destroy, and completes local
cleanup even if the calling task is cancelled.

WebSocket and HTTP are the built-in transports. RabbitMQ, MQTT, nanomsg, Unix
sockets, or an application-specific Janus transport can implement the small
`JanusTransport` protocol and be injected without core interpreting its URL:

```python
from janus_api import JanusSession

session = JanusSession(
    transport=my_transport,
    url="unix:///run/janus.sock",  # owned by the injected transport
)
await session.create()
```

Pass either `transport` or `transport_factory`, never both. A factory-created
transport is owned and closed by the session; a directly injected transport is
treated as shared and remains owned by the host application.

## Authentication

Janus API tokens and API secrets belong to the outer envelope of every request.
Configure them once per session; representations and settings inspection redact
their values.

```python
from janus_api import JanusCredentials, JanusSession

credentials = JanusCredentials(token="client-token", api_secret="shared-secret")

async with JanusSession(credentials=credentials) as session:
    ...
```

A callable returning `JanusCredentials` may be supplied for credential rotation.
The default session manager reads `JANUS_TOKEN` and `JANUS_API_SECRET`.

## Plugin projects

The sibling `plugins/` workspace contains independent distributions:

| Janus plugin | Distribution | Import package | Entry-point name |
|---|---|---|---|
| EchoTest | `janus-echotest-plugin` | `janus_echotest_plugin` | `echotest` |
| VideoCall | `janus-videocall-plugin` | `janus_videocall_plugin` | `videocall` |
| SIP | `janus-sip-plugin` | `janus_sip_plugin` | `sip` |
| NoSIP | `janus-nosip-plugin` | `janus_nosip_plugin` | `nosip` |
| AudioBridge | `janus-audiobridge-plugin` | `janus_audiobridge_plugin` | `audiobridge` |
| VideoRoom | `janus-videoroom-plugin` | `janus_videoroom_plugin` | `videoroom` |
| TextRoom | `janus-textroom-plugin` | `janus_textroom_plugin` | `textroom` |
| Record&Play | `janus-recordplay-plugin` | `janus_recordplay_plugin` | `recordplay` |

Streaming remains in the `plugins/janus-streaming-plugin`
workspace as distribution `janus-api-streaming`, import package
`janus_streaming`, and entry-point name `streaming`.

Installed plugins are discovered lazily through the `janus_api.plugins` entry
point group. Importing Janus Core never scans or executes arbitrary local files
and never imports unrelated named plugins.

```python
from janus_api.lib import Plugin

# Resolves only the installed `echotest` entry point.
echo = Plugin(identifier="echotest", session=session)
await echo.attach()
```

Direct construction of the concrete class is preferred because it gives type
checkers the plugin-specific methods and result types.

## Implementing a custom plugin

Only the generic base and shared protocol primitives are required:

```python
from typing import Literal

from pydantic import BaseModel

from janus_api.lib import Plugin


class StatusRequest(BaseModel):
    request: Literal["status"] = "status"


class MyPlugin(Plugin):
    identifier = "my-plugin"
    name = "janus.plugin.my-plugin"

    async def status(self):
        return await self.send(StatusRequest())
```

To support lazy discovery from a separate distribution:

```toml
[project.entry-points."janus_api.plugins"]
my-plugin = "my_package.plugin:MyPlugin"
```

Plugin response bodies are opaque to core. A plugin package should use strict
outbound models, forward-compatible inbound models, typed plugin errors, and
golden protocol tests derived from its Janus documentation.

## Session pool and ASGI lifecycle

`JanusSessionManager` owns a bounded, process-local session pool. Each ASGI
worker owns its Janus control connections; the old unauthenticated Redis leader
proxy has been removed because it could not safely preserve handle ownership or
unsolicited plugin events across processes.

```python
from janus_api.servers import JanusSessionManager

async with JanusSessionManager(pool_size=2) as manager:
    session = manager.get_session(key="tenant-42")
    if session is None:
        raise RuntimeError("Janus is unavailable")
```

The optional operations application owns its resources transactionally through
ASGI lifespan:

```python
from janus_api import create_asgi_app

app = create_asgi_app(mount_rest_api=True)
```

```bash
JANUS_MOUNT_REST_API=true \
uvicorn myapp:app --host 0.0.0.0 --port 8000
```

When enabled, the `/janus` mount exposes:

- `/manager/` and `/manager/ready` — pool health and readiness (`503` when unavailable)
- `/admin/` — authenticated Admin/Monitor JSON, Prometheus, and WebSocket APIs
- `/events/janus-events` — bounded, Basic-authenticated Janus EventHandler ingestion to Kafka
- `/logs/` and `/logs/ws/logs` — bounded API-key-authenticated structured log access

The Admin surface is deliberately API-first (JSON, Prometheus text, and
WebSocket updates); core does not ship raw, uncompiled frontend source as a
production UI.

Admin, EventHandler, log viewer, Kafka, and Timescale resources are disabled by
default. The service fails closed when an enabled component lacks credentials.
Schema migration is an explicit deployment action, never an import/startup side
effect:

```python
import asyncio

from janus_api.contrib.admin.db import migrate

asyncio.run(migrate())
```

Kafka publication uses `acks=all`, producer idempotence, stable
`janus-event-id` headers, bounded global delivery/admission, and optional
TLS/SASL. Consumers should deduplicate by that header because an HTTP batch can
partially succeed before Janus retries it. Timescale queries have statement,
row, and time-bucket budgets; optional retention and compression policies are
installed by the explicit migration.

Structured file logging is also opt-in. The handler installer is idempotent,
recursively redacts nested credentials, creates restrictive files, and supports
size-based or external watched rotation:

```python
from janus_api.core.logging import install_colored_logging

install_colored_logging(logfile="/var/log/myapp/janus.jsonl", rotation="watched")
```

## Configuration

Copy `.env.example` into the host application's secret-management workflow.
The package itself does not load `.env` files.

| Variable | Default | Purpose |
|---|---:|---|
| `JANUS_SESSION_URL` | `ws://localhost:8188/janus` | WS/WSS or HTTP/HTTPS API endpoint |
| `JANUS_REQUEST_TIMEOUT` | `15` | Per-request timeout in seconds |
| `JANUS_SESSION_POOL_SIZE` | `1` | Sessions per process |
| `JANUS_STARTUP_FAIL_FAST` | `false` | Fail ASGI startup instead of serving degraded readiness |
| `JANUS_KEEPALIVE_INTERVAL` | `25` | WebSocket session keepalive interval |
| `JANUS_KEEPALIVE_FAILURES` | `3` | Failures before a session is invalidated |
| `JANUS_SHUTDOWN_TIMEOUT` | `10` | Total bounded session-shutdown budget |
| `JANUS_DETACH_CONCURRENCY` | `16` | Concurrent handle detach limit |
| `JANUS_TOKEN` | unset | Janus token authentication |
| `JANUS_API_SECRET` | unset | Janus shared API secret |
| `JANUS_MOUNT_REST_API` | `false` | Mount operations API |
| `JANUS_ENABLE_ADMIN` | `false` | Start Admin/Monitor integration |
| `JANUS_ENABLE_EVENTS` | `false` | Start Kafka EventHandler sink |
| `JANUS_MOUNT_LOGGING_APP` | `false` | Enable log query/stream service |
| `JANUS_ALLOWED_ORIGINS` | unset | Exact CORS/WebSocket origins |
| `JANUS_KAFKA_SECURITY_PROTOCOL` | `PLAINTEXT` | `PLAINTEXT`, `SSL`, `SASL_PLAINTEXT`, or `SASL_SSL` |
| `JANUS_KAFKA_DELIVERY_CONCURRENCY` | `32` | Process-wide Kafka send concurrency |
| `JANUS_KAFKA_MAX_INFLIGHT_BATCHES` | `16` | EventHandler HTTP admission limit |
| `JANUS_TIMESCALE_QUERY_TIMEOUT` | `5` | Aggregate query/command timeout |
| `JANUS_TIMESCALE_MAX_QUERY_ROWS` | `10000` | Hard aggregate-result row limit |
| `JANUS_TIMESCALE_RETENTION_DAYS` | `0` | Optional retention policy; `0` disables it |
| `JANUS_TIMESCALE_COMPRESSION_AFTER_DAYS` | `0` | Optional compression policy; `0` disables it |

See `.env.example` for the credentials and endpoints required by optional
services. Use a custom typed module through `JANUS_SETTINGS_MODULE` for more
complex deployments; explicit programmatic overrides are available through
`janus_api.conf.configure`.

## Development and verification

```bash
uv sync --all-extras --group dev
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src/janus_api
uv build
```

The tracked test suite covers protocol validation, credential injection,
session isolation and invalidation, cancellation-safe WebSocket transactions,
REST addressing/long polling, plugin discovery/lifecycle, secure operations
defaults, and the no-named-plugin package boundary. Live Janus media tests are
marked as integration tests and should run against the versions used in each
deployment.

See [the architecture guide](docs/architecture.md) for ownership and runtime
invariants, and [the production checklist](docs/production-checklist.md) for
the real-system gates that cannot be proven by unit tests.

## 2.x migration notes

- Distribution: `janus-api` → `janus-api-core`; import namespace remains `janus_api`.
- `WebsocketSession` remains an alias of the transport-agnostic `JanusSession`.
- Named plugin models, clients, and the old VideoRoom facade moved out of core.
- Streaming moved completely to `janus-api-streaming` under `plugins`.
- Sessions and plugin managers are ordinary instances; process-global singleton
  handles, global Rx event routing, eager plugin scanning, and Redis RPC are gone.
- Plugin payloads are no longer part of a closed core request/response union.
- Root logging, database migrations, threads, sockets, and optional-service
  imports no longer happen at module import time.

## Protocol references

- [Janus transports and core protocol](https://janus.conf.meetecho.com/docs/rest.html)
- [Janus API authentication](https://janus.conf.meetecho.com/docs/auth.html)
- [Admin/Monitor API](https://janus.conf.meetecho.com/docs/admin.html)
- [Event handlers](https://janus.conf.meetecho.com/docs/eventhandlers.html)
- [Recordings](https://janus.conf.meetecho.com/docs/recordings.html)

## License

MIT
