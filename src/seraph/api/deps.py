"""FastAPI dependency injection factories for the Seraph API layer.

Import these with ``Depends(...)`` in route handlers.  Each factory is a
thin wrapper that constructs the service from ``settings`` so routes never
instantiate services directly (keeps them testable via override).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends

from seraph.config import Settings
from seraph.config import settings as _default_settings

# ── Settings ──────────────────────────────────────────────────────────────────


def get_settings() -> Settings:
    """Return the global Settings singleton."""
    return _default_settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


# ── FeedbackDB ────────────────────────────────────────────────────────────────


async def get_feedback_db(cfg: SettingsDep) -> AsyncGenerator:
    """Yield an initialised FeedbackDB instance."""
    from seraph.learning.feedback import FeedbackDB

    db = FeedbackDB(db_path=cfg.sqlite_db_path)
    await db.initialize_schema()
    yield db


FeedbackDBDep = Annotated[object, Depends(get_feedback_db)]


# ── MachineLoader ─────────────────────────────────────────────────────────────


def get_machine_loader(cfg: SettingsDep) -> object:
    """Return a MachineLoader pointed at the default machines.yaml."""
    from seraph.benchmarks.loader import MachineLoader

    return MachineLoader(machines_path=None)


MachineLoaderDep = Annotated[object, Depends(get_machine_loader)]


# ── Qdrant client (raw) ───────────────────────────────────────────────────────


async def get_qdrant_client(cfg: SettingsDep) -> AsyncGenerator:
    """Yield an AsyncQdrantClient, close on teardown."""
    from qdrant_client import AsyncQdrantClient

    client = AsyncQdrantClient(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key or None)
    try:
        yield client
    finally:
        await client.close()


QdrantClientDep = Annotated[object, Depends(get_qdrant_client)]
