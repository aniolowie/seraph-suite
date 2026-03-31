"""Seraph Suite exception hierarchy.

All custom exceptions inherit from SeraphError so callers can catch
any Seraph-specific error with a single `except SeraphError`.
"""

from __future__ import annotations


class SeraphError(Exception):
    """Base exception for all Seraph Suite errors."""


# ── Knowledge Base ────────────────────────────────────────────────────────────


class KnowledgeBaseError(SeraphError):
    """Raised when a knowledge base operation fails."""


class VectorStoreError(KnowledgeBaseError):
    """Qdrant operation failed."""


class GraphStoreError(KnowledgeBaseError):
    """Neo4j operation failed."""


class EmbeddingError(KnowledgeBaseError):
    """Embedding model error."""


class RerankerError(KnowledgeBaseError):
    """Reranker model error."""


# ── Ingestion ─────────────────────────────────────────────────────────────────


class IngestionError(SeraphError):
    """Data ingestion pipeline error."""


class NVDIngestionError(IngestionError):
    """NVD/CVE feed ingestion failed."""


class ExploitDBIngestionError(IngestionError):
    """ExploitDB ingestion failed."""


class WriteupIngestionError(IngestionError):
    """Writeup parsing/ingestion failed."""


class MITREIngestionError(IngestionError):
    """MITRE ATT&CK ingestion failed."""


# ── Agents ────────────────────────────────────────────────────────────────────


class AgentError(SeraphError):
    """Agent execution error."""


class OrchestratorError(AgentError):
    """Orchestrator agent error."""


class ToolExecutionError(AgentError):
    """Tool invocation or output parsing failed."""


class ToolNotFoundError(AgentError):
    """Requested tool is not registered."""


class ToolTimeoutError(ToolExecutionError):
    """Tool execution exceeded its configured timeout."""


class LLMError(AgentError):
    """Anthropic API or LLM response error."""


class LLMRateLimitError(LLMError):
    """Anthropic rate limit hit after max retries."""


# ── Sandbox ───────────────────────────────────────────────────────────────────


class SandboxError(SeraphError):
    """Docker sandbox lifecycle or execution error."""


class ContainerStartError(SandboxError):
    """Container failed to start."""


class CommandTimeoutError(SandboxError):
    """Sandbox command exceeded timeout."""


class ContainerHealthCheckError(SandboxError):
    """Container health check failed after maximum retries."""


class ContainerPoolExhaustedError(SandboxError):
    """All containers in the pool are leased and the wait timeout expired."""


class NetworkSetupError(SandboxError):
    """Docker network creation or configuration failed."""


# ── Self-learning ─────────────────────────────────────────────────────────────


class LearningError(SeraphError):
    """Self-learning loop error."""


class FeedbackError(LearningError):
    """Feedback DB operation failed."""


class HardNegativeError(LearningError):
    """Hard negative mining failed."""


class ProjectionError(LearningError):
    """Query projection layer error."""


class SchedulerError(LearningError):
    """Training scheduler error."""


class FinetuneError(LearningError):
    """LoRA fine-tuning failed."""


# ── Config / API ──────────────────────────────────────────────────────────────


class ConfigError(SeraphError):
    """Configuration validation or loading error."""


class APIError(SeraphError):
    """Internal FastAPI layer error."""


# ── Benchmarking ──────────────────────────────────────────────────────────────


class BenchmarkError(SeraphError):
    """HTB benchmarking harness error."""


class MachineLoadError(BenchmarkError):
    """Failed to load or parse machines.yaml."""


class EngagementRunError(BenchmarkError):
    """Engagement graph invocation failed."""
