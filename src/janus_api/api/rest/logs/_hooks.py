import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from janus_api.api.rest.logs._helpers import build_index, tail_file_and_broadcast


###########################
# FastAPI App Instantiation and Lifespan hooks #
###########################

async def startup_event():
    ...


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await startup_event()
    yield
