# Seraph Suite

> Open-source, local-first AI pentesting agent platform with a self-learning knowledge base.

Seraph Suite is a production-grade agentic system for penetration testing and CTF competition. Each agent is a LangGraph node operating on shared typed state. The knowledge base uses hybrid retrieval (BM25 + dense vectors + Neo4j graph) backed by Qdrant and Neo4j, and continuously improves from engagement feedback via LoRA fine-tuning of the local embedding model.

The benchmark target is HackTheBox machine solve rate and time-to-own.

---

## Table of Contents

- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Phases](#phases)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Agents](#agents)
- [Knowledge Base](#knowledge-base)
- [Self-Learning Loop](#self-learning-loop)
- [Docker Sandbox](#docker-sandbox)
- [Data Ingestion](#data-ingestion)
- [HTB Benchmarking](#htb-benchmarking)
- [Dashboard](#dashboard)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

---

## Architecture

```
CLI (seraph run / bench / ingest)
         │
         ▼
Orchestrator Agent (LangGraph StateGraph)
    ├── Recon Agent          → nmap, subdomain enum, fingerprinting
    ├── Exploit Agent        → CVE matching, Metasploit, custom payloads
    ├── Privesc Agent        → LinPEAS, SUID abuse, sudo misconfigs
    ├── CTF Agent            → flag hunting, steganography, crypto
    └── Memorist Agent       → feedback logging, KB updates
         │
         ▼
Knowledge Base
    ├── Qdrant        → BM25 + dense hybrid search, RRF fusion
    ├── Neo4j         → attack graph, MITRE ATT&CK, Cypher traversal
    └── SQLite        → sessions, feedback logs, ingestion state
         │
         ▼
Self-Learning Loop
    ├── Feedback collection (cited vs ignored docs)
    ├── Hard negative mining
    ├── Triplet accumulation (query, positive, negative)
    └── LoRA adapter training on nomic-embed-text-v1.5

FastAPI layer (Phase 7)
    └── React 18 dashboard (Phase 7)
```

### GraphRAG retrieval pipeline

Every knowledge base query runs through:

1. BM25 sparse search — exact CVE IDs, tool names, error strings
2. Dense semantic search — fuzzy technique descriptions
3. RRF fusion of both result sets
4. Neo4j graph traversal — expand context via MITRE technique/CVE relationships
5. Cross-encoder reranking (bge-reranker-v2-m3) of the top-K fused results

---

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Agent orchestration | LangGraph | StateGraph per agent, tool calling, checkpointing |
| Vector store | Qdrant | Hybrid BM25+dense in one query, RRF fusion |
| Graph store | Neo4j CE | Attack graphs, MITRE ATT&CK mapping, Cypher |
| Metadata / sessions | SQLite | Feedback logs, ingestion state |
| Dense embeddings | nomic-embed-text-v1.5 | 768d, 8192 ctx, Matryoshka, fine-tunable |
| Sparse embeddings | Qdrant BM25 via FastEmbed | Keyword matching for CVE IDs, tool names |
| Reranker | bge-reranker-v2-m3 | Cross-encoder re-scoring |
| LLM reasoning | Claude (Anthropic API) | Primary; OpenRouter as fallback |
| CVE auto-tagger | CWE rules → SetFit → Claude batch | Three-tier classification |
| Agent containers | Docker (aiodocker) | Manus-style isolated compute |
| API layer | FastAPI + uvicorn | Internal REST + WebSocket |
| Config | Pydantic Settings + YAML | Typed config, env overrides |
| Task queue | Celery + Redis | Async ingestion, embedding jobs, retraining |

All embeddings are computed locally — no API calls for embeddings.

---

## Project Structure

```
seraph-suite/
├── pyproject.toml              # Single root project (uv)
├── docker-compose.yml          # Qdrant + Neo4j + Redis + agent containers
├── docker-compose.dev.yml      # Dev overrides
├── .env.example
├── Makefile
│
├── src/seraph/
│   ├── config.py               # Pydantic Settings, all config centralised
│   ├── exceptions.py           # SeraphError hierarchy
│   │
│   ├── agents/                 # LangGraph agent definitions
│   │   ├── orchestrator.py     # Main coordinator
│   │   ├── recon.py            # Recon sub-agent (nmap, subdomain enum)
│   │   ├── exploit.py          # Exploitation sub-agent
│   │   ├── privesc.py          # Privilege escalation sub-agent
│   │   ├── ctf.py              # CTF context sub-agent
│   │   ├── memorist.py         # Self-learning / memory agent
│   │   ├── base_agent.py       # Shared agent base class
│   │   ├── state.py            # EngagementState and related types
│   │   ├── graph_builder.py    # LangGraph graph construction helpers
│   │   ├── llm_client.py       # Anthropic / OpenRouter client wrapper
│   │   └── prompts/            # Jinja2 prompt templates
│   │
│   ├── knowledge/              # Knowledge base layer
│   │   ├── vectorstore.py      # Qdrant client, hybrid search
│   │   ├── graphstore.py       # Neo4j client, Cypher queries
│   │   ├── retriever.py        # GraphRAG: graph + vector fusion
│   │   ├── graph_retriever.py  # Neo4j-specific retrieval logic
│   │   ├── embeddings.py       # Embedding model management + LoRA
│   │   ├── reranker.py         # Cross-encoder reranking
│   │   ├── entity_extractor.py # NER for query entity extraction
│   │   ├── graph_models.py     # Pydantic models for graph entities
│   │   └── graph_queries.py    # Cypher query library
│   │
│   ├── ingestion/              # Data ingestion pipelines
│   │   ├── nvd.py              # NVD/CVE JSON feed
│   │   ├── exploitdb.py        # ExploitDB git mirror
│   │   ├── writeups.py         # Markdown writeup parser
│   │   ├── ctftime.py          # CTFTime scraper
│   │   ├── mitre.py            # MITRE ATT&CK STIX ingestion
│   │   ├── mitre_parser.py     # STIX bundle parser
│   │   ├── chunker.py          # Chunk splitting (respects code blocks)
│   │   ├── models.py           # Ingestion Pydantic models
│   │   ├── state.py            # Ingestion run state
│   │   └── tasks.py            # Celery tasks for async ingestion
│   │
│   ├── learning/               # Self-learning loop
│   │   ├── feedback.py         # Implicit/explicit feedback collection (SQLite)
│   │   ├── negatives.py        # Hard negative mining from retrieval logs
│   │   ├── finetune.py         # LoRA adapter training (PEFT)
│   │   ├── projection.py       # Query-time projection layer
│   │   ├── scheduler.py        # Periodic retraining trigger (Celery beat)
│   │   └── models.py           # Feedback and training record models
│   │
│   ├── sandbox/                # Manus-style agent containers (Phase 5)
│   │   ├── manager.py          # Docker container lifecycle (aiodocker)
│   │   ├── executor.py         # Command execution in sandbox
│   │   ├── pool.py             # Warm container pool
│   │   ├── network.py          # Per-engagement Docker networks
│   │   ├── models.py           # Sandbox state models
│   │   └── Dockerfile.agent    # Base agent container image
│   │
│   ├── tools/                  # Tool wrappers for agents
│   │   ├── nmap.py
│   │   ├── gobuster.py
│   │   ├── sqlmap.py
│   │   ├── metasploit.py
│   │   ├── linpeas.py
│   │   ├── hydra.py
│   │   ├── curl.py
│   │   └── _registry.py        # Tool discovery + RAG-based selection
│   │
│   ├── api/                    # FastAPI internal API (Phase 7)
│   │   ├── app.py
│   │   ├── routes/
│   │   └── schemas.py
│   │
│   └── worker.py               # Celery worker entry point
│
├── src/cli/
│   ├── main.py                 # `seraph` CLI root
│   ├── ingest.py               # `seraph ingest` commands
│   └── bench.py                # `seraph bench` HTB benchmarking
│
├── tests/
│   ├── unit/                   # 40+ unit tests
│   ├── integration/            # Qdrant / Neo4j integration tests
│   └── benchmarks/             # HTB machine solve benchmarks
│       ├── machines.yaml       # Machine definitions (name, IP, flags, techniques)
│       └── test_htb_*.py
│
├── configs/
│   ├── mitre_attack.yaml       # ATT&CK tactic/technique mappings
│   ├── cwe_categories.yaml     # CWE → category rules (Tier 1)
│   ├── tools.yaml              # Tool definitions and capabilities
│   └── agents.yaml             # Agent configuration and tool assignments
│
├── data/                       # Local data — gitignored, populated by ingestion
│   ├── qdrant/
│   ├── neo4j/
│   ├── writeups/
│   └── models/                 # Downloaded models + LoRA adapters
│
└── docs/
    ├── ARCHITECTURE.md
    ├── AGENTS.md
    ├── KNOWLEDGE_BASE.md
    ├── BENCHMARKS.md
    ├── SANDBOX.md
    └── DASHBOARD.md
```

---

## Phases

| Phase | Description | Status |
|---|---|---|
| 1 | Data ingestion + Qdrant hybrid search + basic retrieval | Complete |
| 2 | Neo4j attack graph + MITRE ATT&CK mapping + GraphRAG | Complete |
| 3 | LangGraph agents (orchestrator + recon + exploit + privesc) | Complete |
| 4 | CTF sub-agent + writeup corpus + self-learning loop | Complete |
| 5 | Docker sandbox isolation (Manus-style containers) | Complete |
| 6 | HTB benchmarking harness + public benchmarks | Complete |
| 7 | Dashboard UI + FastAPI layer | Complete |

---

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- Docker + Docker Compose
- An Anthropic API key

### 1. Clone and install

```bash
git clone https://github.com/Unohana/seraph-suite.git
cd seraph-suite
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY and NEO4J_PASSWORD at minimum
uv sync
```

### 2. Start services

```bash
make up
# Qdrant: http://localhost:6333
# Neo4j:  http://localhost:7474  (user: neo4j, pass: from NEO4J_PASSWORD)
# Redis:  localhost:6379
```

### 3. Ingest knowledge base

```bash
# Ingest NVD CVE feed (last 30 days by default)
seraph ingest nvd

# Ingest MITRE ATT&CK STIX bundle
seraph ingest mitre

# Ingest ExploitDB git mirror
seraph ingest exploitdb

# Ingest a directory of CTF writeups (Markdown)
seraph ingest writeups --path ./data/writeups/
```

### 4. Run the CLI

```bash
seraph --help

# Run a pentest engagement
seraph run --target 10.10.10.3

# CTF mode
seraph run --target 10.10.11.42 --mode ctf

# Run with sandbox isolation enabled (requires Docker)
SANDBOX_ENABLED=true seraph run --target 10.10.10.3
```

---

## Configuration

All configuration is driven by environment variables (`.env` file) and validated at startup via Pydantic Settings. See `.env.example` for the full list with descriptions.

Key settings:

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required. Anthropic API key |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant endpoint |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j bolt endpoint |
| `NEO4J_PASSWORD` | — | Required. Neo4j password |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis / Celery broker |
| `DENSE_EMBEDDING_MODEL` | `nomic-ai/nomic-embed-text-v1.5` | Local HuggingFace model ID |
| `RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | Local cross-encoder model |
| `SANDBOX_ENABLED` | `false` | Route all tools through Docker containers |
| `LOG_LEVEL` | `INFO` | structlog level |

---

## Agents

All agents are LangGraph StateGraph nodes. They communicate via a shared `EngagementState` Pydantic model — not via HTTP or message queues.

### EngagementState

```python
class EngagementState(BaseModel):
    target: TargetInfo
    phase: Phase          # recon | enumerate | exploit | privesc | post
    findings: list[Finding]
    attack_graph: list[GraphEdge]
    kb_context: list[RetrievedDoc]
    tool_outputs: list[ToolResult]
    plan: list[PlanStep]
    history: list[AgentAction]
    flags: list[str]      # captured flags (benchmarking)
```

### Agent roles

| Agent | Responsibility | Key tools |
|---|---|---|
| **Orchestrator** | Phase transitions, sub-agent dispatch, plan management | — |
| **Recon** | Port scanning, service fingerprinting, subdomain enum | nmap, gobuster, curl |
| **Exploit** | CVE matching, payload delivery, shell acquisition | metasploit, sqlmap, curl |
| **Privesc** | Privilege escalation, lateral movement | linpeas, hydra |
| **CTF** | Flag hunting, stego, crypto, web challenges | gobuster, curl, custom |
| **Memorist** | KB feedback logging, triplet accumulation | — (internal only) |

### Tool selection

When more than 20 tools are available, the agent uses RAG-based tool selection: tool descriptions are embedded locally, and only the top-K most relevant tools are passed to the LLM for the current subtask.

### Prompt templates

All prompts live in `src/seraph/agents/prompts/` as Jinja2 templates. They use XML tag structure (`<target_info>`, `<findings>`, `<kb_context>`) and include few-shot examples for technique extraction and attack planning.

---

## Knowledge Base

### Supported data sources

| Source | Ingester | Content |
|---|---|---|
| NVD CVE feed | `ingestion/nvd.py` | CVE descriptions, CVSS scores, CWE tags |
| ExploitDB | `ingestion/exploitdb.py` | Exploit headers and metadata |
| CTF writeups | `ingestion/writeups.py` | Markdown writeups with front matter |
| CTFTime | `ingestion/ctftime.py` | Event and writeup index |
| MITRE ATT&CK | `ingestion/mitre.py` | Techniques, tactics, mitigations (STIX) |

### Chunking rules

- 200–500 tokens for writeups and CVE descriptions.
- Never split inside a code block.
- Every chunk is prefixed with source context: `[CVE-2021-44228] ...` or `[T1059.001] ...`
- CVSS scores, dates, and structured metadata go into Qdrant payload filters, not embeddings.

### Neo4j attack graph

Nodes: `Technique`, `Tactic`, `CVE`, `Tool`, `Machine`, `Engagement`

Edges: `USES`, `EXPLOITS`, `MITIGATES`, `BELONGS_TO`, `PRECEDED_BY`

The GraphRAG pipeline extracts entities from the query, traverses the graph for related techniques and CVEs, then uses those entities as Qdrant payload filters before vector search.

---

## Self-Learning Loop

Seraph improves its retrieval quality with every engagement:

1. **Feedback logging** — The Memorist agent records which retrieved documents were cited by the LLM vs ignored, stored in SQLite.
2. **Hard negative mining** — `learning/negatives.py` identifies keyword-similar but semantically wrong retrievals from the feedback log.
3. **Triplet accumulation** — `(query, positive_doc, hard_negative)` triplets are accumulated in SQLite.
4. **LoRA fine-tuning** — `learning/finetune.py` trains a LoRA adapter on `nomic-embed-text-v1.5` using the accumulated triplets (PEFT library).
5. **Projection layer** — `learning/projection.py` applies a learned linear projection at query time, avoiding full corpus re-embedding after each training run.
6. **Scheduled retraining** — `learning/scheduler.py` triggers Celery beat tasks when enough new triplets accumulate.

This feedback loop is the core differentiator over static RAG — retrieval quality improves with use.

---

## Docker Sandbox

Phase 5 adds Manus-style container isolation. Each tool invocation runs inside a short-lived Docker container:

- **Isolated network** — each engagement gets its own Docker bridge network scoped to the target IP
- **Warm pool** — `sandbox/pool.py` maintains `SANDBOX_POOL_SIZE` pre-warmed containers for low latency
- **Resource limits** — CPU and memory capped per container via `SANDBOX_CPU_LIMIT` / `SANDBOX_MEMORY_LIMIT_MB`
- **Automatic cleanup** — containers are destroyed on engagement end or after `SANDBOX_CONTAINER_TIMEOUT` seconds

Enable with `SANDBOX_ENABLED=true` in `.env`. Build the agent image:

```bash
make sandbox-build
make sandbox-test   # requires Docker
```

---

## Data Ingestion

```bash
# All ingestion commands
seraph ingest --help

seraph ingest nvd                          # NVD CVE JSON feed
seraph ingest exploitdb                    # ExploitDB git mirror
seraph ingest mitre                        # MITRE ATT&CK STIX bundle
seraph ingest writeups --path <dir>        # Markdown writeup directory
seraph ingest ctftime --event-id <id>      # Single CTFTime event

# Or trigger via Celery
make worker   # start Celery worker
# Then ingest tasks are dispatched asynchronously
```

All ingestion is idempotent — re-running will skip already-processed items tracked in SQLite.

---

## HTB Benchmarking

### Machine registry

Define target machines in `tests/benchmarks/machines.yaml`:

```yaml
machines:
  - name: Lame
    ip: 10.10.10.3
    os: Linux
    difficulty: Easy
    flags:
      user: <hash>
      root: <hash>
    expected_techniques: [T1210, T1068]
```

### Running benchmarks

```bash
# Single machine
seraph bench --machine Lame --timeout 3600

# All Easy machines
seraph bench --difficulty Easy --all --report

# Generate report
seraph bench --machine Lame --report-dir ./data/reports/
```

### Metrics

- **Solve rate** — % of machines where root flag is captured
- **Time-to-own** — wall-clock from start to root flag
- **Technique accuracy** — did the agent use expected/optimal techniques?
- **KB utilisation** — ratio of retrieved docs cited by the LLM
- **Learning curve** — solve rate improvement over successive engagements on the same machine class

---

## Dashboard

Phase 7 adds a FastAPI REST + WebSocket layer and a React 18 SPA.

```bash
# Start the API
make api-dev

# Start the dashboard dev server
make dashboard-dev
# Dashboard: http://localhost:5173

# Build for production
make dashboard-build
```

API endpoints:

| Endpoint | Description |
|---|---|
| `GET /api/health` | Service health (Qdrant, Neo4j, Redis) |
| `GET/POST /api/engagements` | Engagement registry + live WebSocket feed |
| `GET /api/benchmarks` | Run history + trigger Celery benchmark task |
| `GET /api/knowledge` | Collection stats + ingestion status |
| `GET /api/learning` | Feedback stats + training history |
| `GET/PUT /api/machines` | Machine registry CRUD |
| `POST /api/writeups` | Markdown upload + async ingest |

Rate limiting: token-bucket middleware at `API_RATE_LIMIT_PER_MINUTE` requests per IP. WebSocket upgrade paths are exempt.

---

## Development

### Setup

```bash
uv sync --all-extras
make dev    # Start services with dev overrides (embedded Qdrant)
```

### Running tests

```bash
make test           # unit + integration + coverage report
make test-unit      # unit tests only
pytest tests/unit/test_feedback_db.py -v   # single file
```

Coverage must remain above 80%.

### Linting and formatting

```bash
make lint     # ruff check
make format   # ruff format
```

### Before every commit checklist

- [ ] `make lint` — no errors
- [ ] `make format` — formatted
- [ ] `make test-unit` — all pass
- [ ] Update `docs/` if public API changed

### LLM model selection

| Task | Model |
|---|---|
| Agent reasoning (default) | `claude-sonnet-4-20250514` |
| Complex multi-step planning | `claude-opus-4-20250514` |
| CVE auto-tagging (batch) | Claude batch API |

---

## Contributing

Contributions are welcome. Please open an issue before submitting a large PR so we can align on direction.

1. Fork the repo and create a branch: `phase-N/your-feature`
2. Follow the coding conventions in the codebase (type hints everywhere, Pydantic v2, async I/O, structlog)
3. Write tests first (TDD) — 80% coverage minimum
4. Run `make lint && make test-unit` before pushing
5. Open a PR with a clear description

---

## License

MIT — see [LICENSE](LICENSE).
