"""Create the FastAPI application and own its dependency lifespan."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import Settings
from app.dependencies import application_container_lifespan
from app.transport.chat_api import router as chat_router


def create_app(settings: Settings) -> FastAPI:
    """Create one application whose container lives for the app lifespan."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        async with application_container_lifespan(settings) as container:
            application.state.application_container = container
            yield

    application = FastAPI(lifespan=lifespan)
    application.include_router(chat_router)
    return application


app = create_app(
    Settings(
        pos_base_url=os.getenv("BOOKING_API_URL", "http://localhost:8000"),
    )
)
