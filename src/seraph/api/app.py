"""FastAPI application factory for the Seraph API layer.

Usage::

    uvicorn seraph.api.app:create_app --factory --reload
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from seraph.api.middleware import LoggingMiddleware, RateLimitMiddleware
from seraph.api.schemas import ErrorResponse
from seraph.config import settings
from seraph.exceptions import SeraphError

log = structlog.get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    log.info("api.startup", cors_origins=settings.cors_origins)
    # Future: warm-up Qdrant client pool, initialise FeedbackDB, etc.
    yield
    log.info("api.shutdown")


def create_app() -> FastAPI:
    """Construct and return the FastAPI application.

    Returns:
        Configured FastAPI instance ready for uvicorn.
    """
    app = FastAPI(
        title="Seraph Suite API",
        version="0.7.0",
        description="Internal API for the Seraph AI pentesting agent suite.",
        lifespan=_lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Rate limiting ─────────────────────────────────────────────────────────
    app.add_middleware(RateLimitMiddleware, limit=settings.api_rate_limit_per_minute)

    # ── Request logging ───────────────────────────────────────────────────────
    app.add_middleware(LoggingMiddleware)

    # ── Global exception handler ──────────────────────────────────────────────
    @app.exception_handler(SeraphError)
    async def seraph_error_handler(request: Request, exc: SeraphError) -> JSONResponse:
        log.error("api.seraph_error", path=request.url.path, error=str(exc))
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error=type(exc).__name__,
                detail=str(exc),
                path=request.url.path,
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        log.error("api.unhandled_error", path=request.url.path, error=str(exc))
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="InternalServerError",
                detail="An unexpected error occurred.",
                path=request.url.path,
            ).model_dump(),
        )

    # ── Routers ───────────────────────────────────────────────────────────────
    from seraph.api.routes.benchmarks import router as benchmarks_router
    from seraph.api.routes.engagements import router as engagements_router
    from seraph.api.routes.health import router as health_router
    from seraph.api.routes.knowledge import router as knowledge_router
    from seraph.api.routes.learning import router as learning_router
    from seraph.api.routes.machines import router as machines_router
    from seraph.api.routes.writeups import router as writeups_router

    app.include_router(health_router)
    app.include_router(engagements_router)
    app.include_router(benchmarks_router)
    app.include_router(knowledge_router)
    app.include_router(learning_router)
    app.include_router(machines_router)
    app.include_router(writeups_router)

    return app
