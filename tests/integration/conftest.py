"""Shared fixtures for integration tests.

Integration tests require running Docker services:
    make up

All integration tests are marked with @pytest.mark.integration and
skip gracefully when Qdrant is unavailable.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

# Register the integration mark.
pytest.ini_options = {}  # type: ignore[assignment]


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "integration: requires Docker services (Qdrant, Neo4j, Redis)"
    )


async def _qdrant_available(url: str) -> bool:
    """Return True if Qdrant is reachable."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{url}/readyz")
            return resp.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="session")
def qdrant_url() -> str:
    return "http://localhost:6333"


@pytest.fixture
async def qdrant_store(qdrant_url: str):  # type: ignore[no-untyped-def]
    """Provide a QdrantStore with a unique test collection that is torn down after the test."""
    from seraph.knowledge.vectorstore import QdrantStore

    if not await _qdrant_available(qdrant_url):
        pytest.skip("Qdrant not available — run `make up` first")

    collection_name = f"seraph_test_{int(time.time() * 1000)}"
    store = QdrantStore(url=qdrant_url, collection_name=collection_name)
    await store.ensure_collection()
    yield store
    # Teardown: delete the test collection.
    try:
        await store._client.delete_collection(collection_name)
    except Exception:
        pass
    await store.close()


async def _neo4j_available(uri: str, user: str, password: str) -> bool:
    """Return True if Neo4j is reachable."""
    try:
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        async with driver.session() as session:
            await session.run("RETURN 1")
        await driver.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def neo4j_uri() -> str:
    import os

    return os.environ.get("NEO4J_TEST_URI", "bolt://localhost:7687")


@pytest.fixture(scope="session")
def neo4j_creds() -> tuple[str, str]:
    import os

    user = os.environ.get("NEO4J_TEST_USER", "neo4j")
    password = os.environ.get("NEO4J_TEST_PASSWORD", "password")
    return user, password


@pytest.fixture
async def neo4j_store(neo4j_uri: str, neo4j_creds: tuple[str, str]):  # type: ignore[no-untyped-def]
    """Provide a Neo4jStore connected to a test Neo4j instance.

    Tears down all nodes after each test.  Skips if Neo4j is unavailable.
    """
    from seraph.knowledge.graphstore import Neo4jStore

    user, password = neo4j_creds
    if not await _neo4j_available(neo4j_uri, user, password):
        pytest.skip("Neo4j not available — run `make up` first")

    store = Neo4jStore(uri=neo4j_uri, user=user, password=password)
    await store.ensure_schema()
    yield store
    # Teardown: wipe all test data
    try:
        driver = store._get_driver()
        async with driver.session() as session:
            await session.run("MATCH (n) DETACH DELETE n")
    except Exception:
        pass
    await store.close()


@pytest.fixture
async def ingestion_db(tmp_path: Path):  # type: ignore[no-untyped-def]
    """Provide a fresh IngestionStateDB backed by a temp file."""
    from seraph.ingestion.state import IngestionStateDB

    db = IngestionStateDB(db_path=tmp_path / "test_state.db")
    await db.init_db()
    return db
