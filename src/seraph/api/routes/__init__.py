"""FastAPI route modules."""

from __future__ import annotations

from seraph.api.routes.benchmarks import router as benchmarks_router
from seraph.api.routes.engagements import router as engagements_router
from seraph.api.routes.health import router as health_router
from seraph.api.routes.knowledge import router as knowledge_router
from seraph.api.routes.learning import router as learning_router
from seraph.api.routes.machines import router as machines_router
from seraph.api.routes.writeups import router as writeups_router

__all__ = [
    "benchmarks_router",
    "engagements_router",
    "health_router",
    "knowledge_router",
    "learning_router",
    "machines_router",
    "writeups_router",
]
