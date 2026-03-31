"""Unit tests for the exception hierarchy."""

from __future__ import annotations

import pytest

from seraph.exceptions import (
    AgentError,
    CommandTimeoutError,
    EmbeddingError,
    IngestionError,
    KnowledgeBaseError,
    NVDIngestionError,
    SandboxError,
    SeraphError,
    ToolNotFoundError,
    VectorStoreError,
)


class TestExceptionHierarchy:
    def test_seraph_error_is_base(self) -> None:
        with pytest.raises(SeraphError):
            raise SeraphError("base error")

    def test_knowledge_base_error_inherits_seraph(self) -> None:
        with pytest.raises(SeraphError):
            raise KnowledgeBaseError("kb error")

    def test_vector_store_error_inherits_kb(self) -> None:
        with pytest.raises(KnowledgeBaseError):
            raise VectorStoreError("qdrant error")

    def test_nvd_ingestion_inherits_ingestion(self) -> None:
        with pytest.raises(IngestionError):
            raise NVDIngestionError("nvd error")

    def test_command_timeout_inherits_sandbox(self) -> None:
        with pytest.raises(SandboxError):
            raise CommandTimeoutError("timed out")

    def test_tool_not_found_inherits_agent(self) -> None:
        with pytest.raises(AgentError):
            raise ToolNotFoundError("tool missing")

    def test_all_inherit_seraph_error(self) -> None:
        errors = [
            VectorStoreError("e"),
            EmbeddingError("e"),
            NVDIngestionError("e"),
            AgentError("e"),
            ToolNotFoundError("e"),
            CommandTimeoutError("e"),
        ]
        for err in errors:
            assert isinstance(err, SeraphError), f"{type(err)} must inherit SeraphError"
