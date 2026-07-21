import asyncio
import logging
from contextlib import asynccontextmanager
from typing import TypedDict, Required, AsyncIterator, Type, NotRequired

from aiokafka import AIOKafkaProducer
from starlette.applications import Starlette

from janus_api.api.rest.logs._helpers import build_index, tail_file_and_broadcast
from janus_api.conf import Janus, settings
from janus_api.contrib.admin import JanusAdminMonitor, TimescaleStorage, MonitorFilter
from janus_api.contrib.admin.db import migrate
from janus_api.core import PersistentJanusPluginManager
from janus_api.servers import JanusSessionManager

logger = logging.getLogger(__name__)

JANUS_ENABLE_ADMIN = getattr(settings, "JANUS_ENABLE_ADMIN")
JANUS_ENABLE_EVENTS = getattr(settings, "JANUS_ENABLE_EVENTS")
JANUS_ADMIN_WS_URL = getattr(settings, "JANUS_ADMIN_WS_URL",
                             "ws://127.0.0.1:7088/admin")  # replace with your janus admin ws
JANUS_ADMIN_SECRET = getattr(settings, "JANUS_ADMIN_SECRET", None)  # set to your admin_secret if configured
DSN = getattr(settings, "TIMESCALE_DSN", None)
KAFKA_BOOTSTRAP = getattr(settings, "KAFKA_BOOTSTRAP")


class State(TypedDict, total=False):
    janus: Required[Type[Janus]]
    ppm: Required[PersistentJanusPluginManager]
    monitor: NotRequired[JanusAdminMonitor | None]
    storage: NotRequired[TimescaleStorage | None]
    producer: NotRequired[AIOKafkaProducer|None]


# 4. Define the Lifespan Context Manager
@asynccontextmanager
async def lifespan(_asgi_app: Starlette) -> AsyncIterator[State]:
    jsm = JanusSessionManager()
    ppm = PersistentJanusPluginManager.instance()

    # Expose globally
    Janus.set_manager(jsm)
    # --- STARTUP LOGIC ---
    logger.info(">>> LIFESPAN HOOK: STARTING UP JANUS SERVER <<<")

    try:
        await jsm.start()
        logger.info(">>> LIFESPAN HOOK: JANUS SERVER STARTED")
    except Exception as exc:
        logger.exception(">>> LIFESPAN HOOK: JANUS SERVER STARTUP FAILED DUE TO %s REASONS <<<", exc, exc_info=exc)
        raise  # Stop startup if critical component fails

    monitor = None
    storage = None
    producer = None
    if JANUS_ENABLE_ADMIN:
        logger.info(">>> Running TimescaleStorage DB Migration <<<")
        try:
            await migrate()
        except Exception as e:
            logger.warning(">>> TimescaleStorage DB Migration failed due to %s, skipping... <<<", e, exc_info=e)

        storage = TimescaleStorage(dsn=DSN)  # type: ignore
        monitor = JanusAdminMonitor()

        logger.info(">>> connecting to Timescale Storage DB <<<")
        try:
            await storage.connect()
        except Exception as err:
            logger.error(">>> Timescale Storage DB connection failed: %s <<<", str(err), exc_info=err)
            raise
        try:
            await monitor.connect()
        except Exception as err:
            logger.error("Janus Admin monitor connection failed: %s", str(err), exc_info=err)
            raise
        # example: filter only videoroom plugin publishers
        monitor.set_filter(MonitorFilter(
            plugins_included={"janus.plugin.videoroom"},
            only_publisher=True)
        )

        logger.info(">>> Polling Janus Monitor for events <<<")
        try:
            await monitor.start_polling()
        except Exception as err:
            logger.error(">>> Janus monitor polling failed: %s <<<", str(err), exc_info=err)

        logger.info(">>> ADMIN LIFESPAN STARTED: MONITOR & TIMESCALE STORAGE CONNECTED <<<")

    if JANUS_ENABLE_EVENTS:
        producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
        )
        try:
            await producer.start()
            logger.info(">>> AIOKafkaProducer started, bootstrap=%s <<<", KAFKA_BOOTSTRAP)
        except Exception as err:
            logger.exception("Error occurred while bootstrapping KAFKA due to %s", str(err), exc_info=err)

    try:
        logger.info(">>> Building logging index <<<")
        await build_index()
        asyncio.create_task(tail_file_and_broadcast())
    except Exception as err:
        logger.debug(err)

    # Yield control back to the application (Server runs here)
    yield State(
        janus=Janus,
        ppm=ppm,
        monitor=monitor,
        storage=storage,
        producer=producer
    )

    # --- SHUTDOWN ---

    if producer:
        await producer.stop()
        logger.info(">>> AIOKafkaProducer stopped <<<")

    if monitor:
        logger.warning(">>> ADMIN LIFESPAN SHUTDOWN: MONITOR & TIMESCALE STORAGE DISCONNECTED <<<")
        try:
            await monitor.close()
        except Exception as err:
            logger.error("Janus monitor close failed: %s", str(err), exc_info=err)

    if storage:
        try:
            await storage.close()
        except Exception as err:
            logger.error("Timescale DB Storage close failed: %s", str(err), exc_info=err)

    logger.info(">>> LIFESPAN HOOK: SHUTTING DOWN JANUS SERVER <<<")

    # C. Detach Plugins
    try:
        await ppm.close()
        logger.info(f">>> GLOBAL PERSISTENT PLUGIN MANAGER CLOSED: {repr(ppm)!r} <<<")
    except Exception as exc:
        logger.exception(">>> ERROR SHUTTING DOWN GLOBAL PERSISTENT PLUGIN MANAGER <<<", exc_info=exc)

    try:
        await jsm.stop()
        logger.info(">>> GLOBAL PLUGIN MANAGER STOPPED <<<")
    except Exception as exc:
        logger.exception(">>> ERROR STOPPING GLOBAL PLUGIN MANAGER <<<", exc_info=exc)
