"""ASGI middleware for the Seraph API layer.

Provides:
- Structured request/response logging via structlog.
- Token-bucket rate limiting per remote IP (WebSocket paths exempt).
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

log = structlog.get_logger(__name__)

# WebSocket upgrade paths are exempt from rate limiting.
_WS_PATH_PREFIX = "/api/engagements/"


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request with method, path, status, and duration."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Log the request before and after dispatch."""
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        log.info(
            "http.request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
            client=request.client.host if request.client else "unknown",
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket rate limiter keyed by remote IP.

    Each IP gets ``limit`` tokens that refill at ``limit`` per 60 seconds.
    WebSocket upgrade requests (path starts with ``/api/engagements/`` and
    header ``Upgrade: websocket``) are always allowed through.

    Args:
        app: The ASGI application to wrap.
        limit: Maximum requests per minute per IP.
    """

    def __init__(self, app: object, limit: int = 60) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._limit = limit
        # {ip: [token_count, last_refill_time]}
        self._buckets: dict[str, list[float]] = defaultdict(
            lambda: [float(limit), time.monotonic()]
        )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Allow or reject the request based on token-bucket state."""
        # Exempt WebSocket upgrades.
        is_ws = request.headers.get("upgrade", "").lower() == "websocket"
        if is_ws and request.url.path.startswith(_WS_PATH_PREFIX):
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        bucket = self._buckets[ip]
        now = time.monotonic()

        # Refill tokens proportionally to elapsed time.
        elapsed = now - bucket[1]
        bucket[0] = min(float(self._limit), bucket[0] + elapsed * (self._limit / 60.0))
        bucket[1] = now

        if bucket[0] < 1.0:
            log.warning("rate_limit.exceeded", ip=ip, path=request.url.path)
            return JSONResponse(
                status_code=429,
                content={"error": "Too many requests", "detail": "Rate limit exceeded"},
            )

        bucket[0] -= 1.0
        return await call_next(request)
