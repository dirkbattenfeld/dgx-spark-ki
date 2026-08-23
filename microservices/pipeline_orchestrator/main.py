from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI

from applications.rag.pipelines.config import ENABLED_PIPELINES
from libs.fastapibridge.router import router as pipeline_router
from libs.pipeline.registry import registry
from libs.observability.config import ChannelConfig, ObservabilityConfig
from libs.observability.setup import configure_observability
from libs.observability.middleware import (
    ObservabilityExceptionMiddleware,
    global_exception_handler
)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Observability konfigurieren
    obs_config = ObservabilityConfig(
        service_name="Pipeline-Orchestrator",
        global_log_level="INFO",
        otlp_enabled=False,
        channels={
            "trace": ChannelConfig(enabled_sinks=["console"], log_level="INFO"),
            "data": ChannelConfig(enabled_sinks=["console"], log_level="INFO"),
            "system": ChannelConfig(enabled_sinks=["console"], log_level="INFO"),
        }
    )
    configure_observability(obs_config)
    
    # Lifespan Bootstrap: Registriert die in config.py hinterlegten Pipelines
    registry.bootstrap(ENABLED_PIPELINES)
    yield


app = FastAPI(
    title="Generic Pipeline API Bridge",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(ObservabilityExceptionMiddleware)
app.exception_handler(Exception)(global_exception_handler)

app.include_router(pipeline_router)
