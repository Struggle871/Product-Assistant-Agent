from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from app.api.admin import router as admin_router
from app.api.rag import router as rag_router
from app.config import get_settings
from app.health import readiness
from app.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    yield


app = FastAPI(
    title=get_settings().app_name,
    version="0.1.0",
    description="Foundation API for the multimodal Product Assistant Agent.",
    lifespan=lifespan,
)
app.include_router(admin_router)
app.include_router(rag_router)


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {"service": "product-assistant-backend", "status": "ok"}


@app.get("/api/v1/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/health/ready", tags=["health"])
async def readiness_probe() -> JSONResponse:
    ok, dependencies = await readiness()
    payload: dict[str, Any] = {
        "status": "ready" if ok else "not_ready",
        "dependencies": {
            dependency.name: {
                "status": "ok" if dependency.ok else "error",
                "detail": dependency.detail,
            }
            for dependency in dependencies
        },
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload,
    )
