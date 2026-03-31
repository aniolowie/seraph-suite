# Seraph Suite — Architecture

> Work in progress. Updated as each phase ships.

## Overview

Seraph Suite is a local-first, self-learning AI pentesting agent platform.
Each agent is a LangGraph node operating on a shared `EngagementState`.
The knowledge base uses hybrid retrieval (BM25 + dense + graph) backed by
Qdrant and Neo4j.

## Phase Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Data ingestion + Qdrant hybrid search | Complete |
| 2 | Neo4j attack graph + MITRE + GraphRAG | Complete |
| 3 | LangGraph agents (orchestrator + sub-agents) | Complete |
| 4 | CTF agent + self-learning loop | Complete |
| 5 | Docker sandbox isolation | Complete |
| 6 | HTB benchmarking harness | Complete |
| 7 | Dashboard UI + FastAPI layer | Complete |

## Component Diagram

```
CLI (seraph run / bench / ingest)
         │
         ▼
Orchestrator Agent (LangGraph StateGraph)
    ├── Recon Agent
    ├── Enumerate Agent
    ├── Exploit Agent
    ├── Privesc Agent
    └── Memorist Agent (feedback loop)
         │
         ▼
Knowledge Base
    ├── Qdrant (BM25 + dense hybrid)
    ├── Neo4j (attack graph, MITRE ATT&CK)
    └── SQLite (sessions, feedback logs)
```

## Data Flow

1. User invokes `seraph run --target <IP>`
2. Orchestrator initialises `EngagementState`
3. Recon agent dispatched → Nmap scan → findings added to state
4. Orchestrator decides next phase → dispatches enumerate/exploit/privesc
5. Each agent queries KB for relevant techniques (GraphRAG)
6. Memorist logs which KB docs were useful → accumulates training signal
7. Periodic LoRA fine-tune improves embedding model

See `docs/AGENTS.md` for agent-level details.

## Phase 7 — Dashboard UI

The dashboard adds a FastAPI REST+WebSocket layer and a React 18 SPA:

```
Browser (React 18 SPA)
         │  HTTP REST + WebSocket (/api/*)
         ▼
FastAPI app (uvicorn)
    ├── /api/health          Service health checks (Qdrant, Neo4j, Redis)
    ├── /api/engagements     Engagement registry + live WS feed
    ├── /api/benchmarks      Run history + trigger Celery task
    ├── /api/knowledge       Collection stats + ingestion status
    ├── /api/learning        Feedback stats + training history
    ├── /api/machines        YAML machine registry CRUD
    └── /api/writeups        Markdown upload + async ingest task
         │
         ▼
Existing Seraph backend (Qdrant, Neo4j, SQLite, Celery)
```

### Rate limiting

A token-bucket middleware (`RateLimitMiddleware`) limits each remote IP to
`API_RATE_LIMIT_PER_MINUTE` requests per minute. WebSocket upgrade paths are
exempt to allow persistent connections.

### Docker topology

```
docker-compose services:
  qdrant (6333)  neo4j (7474/7687)  redis (6379)
       │                │               │
       └───────────────┬───────────────┘
                       ▼
                  api (8000)   ← FastAPI + uvicorn
                       │
                  dashboard (80) ← nginx + React SPA
                                   proxies /api/* → api:8000
```

See `docs/DASHBOARD.md` for dashboard-specific details.
