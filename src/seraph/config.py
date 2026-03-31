"""Centralised configuration for Seraph Suite.

All settings are loaded from environment variables (with .env file support).
Import the singleton `settings` object wherever config is needed.

    from seraph.config import settings
    print(settings.qdrant_url)
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    """Main Seraph Suite configuration.

    Values are loaded from environment variables first, then from a .env
    file in the project root.  All secrets must come from env — never
    hardcoded.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── General ───────────────────────────────────────────────────────────────
    env: Environment = Environment.DEVELOPMENT
    log_level: LogLevel = LogLevel.INFO

    # ── LLM APIs ──────────────────────────────────────────────────────────────
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    openrouter_api_key: str = Field(default="", description="OpenRouter fallback key")

    # ── Qdrant ────────────────────────────────────────────────────────────────
    qdrant_url: str = Field(default="http://localhost:6333")
    qdrant_api_key: str = Field(default="")
    qdrant_collection_name: str = Field(default="seraph_kb")

    # ── Neo4j ─────────────────────────────────────────────────────────────────
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(..., description="Neo4j password")

    # ── Redis / Celery ────────────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0")
    celery_broker_url: str = Field(default="redis://localhost:6379/0")
    celery_result_backend: str = Field(default="redis://localhost:6379/1")

    # ── Embedding / Reranker models ───────────────────────────────────────────
    dense_embedding_model: str = Field(default="nomic-ai/nomic-embed-text-v1.5")
    reranker_model: str = Field(default="BAAI/bge-reranker-v2-m3")
    models_dir: Path = Field(default=Path("./data/models"))

    # ── Retrieval ─────────────────────────────────────────────────────────────
    max_retrieval_docs: int = Field(default=20, ge=1, le=100)
    rerank_top_k: int = Field(default=5, ge=1, le=50)

    # ── Agent runtime ─────────────────────────────────────────────────────────
    agent_max_iterations: int = Field(default=15, ge=1, le=100)
    tool_selection_top_k: int = Field(default=5, ge=1, le=20)
    tool_selection_threshold: int = Field(
        default=20,
        ge=1,
        description="RAG-based tool selection activates when tool count exceeds this.",
    )
    default_tool_timeout: int = Field(default=300, ge=10, le=7200)
    llm_cache_enabled: bool = Field(default=True)
    llm_cache_ttl_seconds: int = Field(default=3600, ge=60)
    sonnet_model: str = Field(default="claude-sonnet-4-20250514")
    opus_model: str = Field(default="claude-opus-4-20250514")

    # ── Self-learning / LoRA ──────────────────────────────────────────────────
    lora_rank: int = Field(default=8, ge=1, le=64)
    lora_alpha: int = Field(default=16, ge=1)
    lora_target_modules: list[str] = Field(
        default_factory=lambda: ["query", "key", "value"],
        description="Transformer module names to attach LoRA adapters to.",
    )
    training_batch_size: int = Field(default=16, ge=1, le=512)
    training_epochs: int = Field(default=3, ge=1, le=20)
    training_learning_rate: float = Field(default=2e-4, gt=0.0)
    min_triplets_for_training: int = Field(
        default=50,
        ge=10,
        description="Minimum triplets required before a LoRA training run is triggered.",
    )
    training_schedule_hours: int = Field(
        default=6,
        ge=1,
        description="How often (in hours) the Celery beat task checks for training.",
    )
    lora_adapter_dir: Path = Field(default=Path("./data/models/lora_adapters"))
    projection_model_path: Path = Field(default=Path("./data/models/query_projection.pt"))

    # ── Sandbox / Docker isolation ────────────────────────────────────────────
    sandbox_enabled: bool = Field(
        default=False,
        description="Enable Docker sandbox for agent tool execution.",
    )
    sandbox_image: str = Field(default="seraph-agent:latest")
    sandbox_cpu_limit: float = Field(default=1.0, ge=0.25, le=8.0)
    sandbox_memory_limit_mb: int = Field(default=512, ge=128, le=8192)
    sandbox_pool_size: int = Field(default=3, ge=1, le=20)
    sandbox_pool_timeout_seconds: int = Field(default=30, ge=5, le=120)
    sandbox_container_timeout: int = Field(default=3600, ge=60, le=14400)
    sandbox_data_volume: Path = Field(default=Path("./data"))
    sandbox_network_name: str = Field(default="seraph-agent-net")

    # ── API / Dashboard ───────────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"],
        description="Allowed CORS origins for the dashboard.",
    )
    api_rate_limit_per_minute: int = Field(
        default=60,
        ge=1,
        description="Max HTTP requests per IP per minute (WebSocket exempt).",
    )
    reports_dir: Path = Field(
        default=Path("./data/reports"),
        description="Directory where benchmark JSON reports are saved and served.",
    )

    # ── HTB Benchmarking ──────────────────────────────────────────────────────
    htb_vpn_interface: str = Field(default="tun0")
    htb_api_token: str = Field(default="")

    # ── NVD ───────────────────────────────────────────────────────────────────
    nvd_api_key: str = Field(default="")
    nvd_api_base_url: str = Field(default="https://services.nvd.nist.gov/rest/json/cves/2.0")

    # ── Ingestion ─────────────────────────────────────────────────────────────
    sqlite_db_path: Path = Field(default=Path("./data/seraph_state.db"))
    ingestion_batch_size: int = Field(default=100, ge=1, le=2000)
    exploitdb_mirror_path: Path = Field(default=Path("./data/exploitdb"))
    sparse_embedding_model: str = Field(default="Qdrant/bm25")
    mitre_stix_path: Path = Field(
        default=Path("./data/mitre/enterprise-attack.json"),
        description="Local path for the MITRE ATT&CK Enterprise STIX bundle",
    )

    @field_validator(
        "models_dir",
        "sqlite_db_path",
        "exploitdb_mirror_path",
        "mitre_stix_path",
        "lora_adapter_dir",
        "projection_model_path",
        "sandbox_data_volume",
        "reports_dir",
        mode="before",
    )
    @classmethod
    def expand_path(cls, v: str | Path) -> Path:
        """Resolve relative paths against CWD at startup."""
        return Path(v).expanduser().resolve()

    @field_validator("rerank_top_k")
    @classmethod
    def rerank_top_k_lte_max(cls, v: int, info: object) -> int:
        """rerank_top_k must not exceed max_retrieval_docs."""
        # Pydantic v2: use info.data for cross-field validation
        data = getattr(info, "data", {})
        max_docs = data.get("max_retrieval_docs", 20)
        if v > max_docs:
            raise ValueError(f"rerank_top_k ({v}) must be ≤ max_retrieval_docs ({max_docs})")
        return v


# Module-level singleton — import this everywhere.
settings: Settings = Settings()  # type: ignore[call-arg]
