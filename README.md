
```
  ███████╗███████╗██████╗  █████╗ ██████╗ ██╗  ██╗
  ██╔════╝██╔════╝██╔══██╗██╔══██╗██╔══██╗██║  ██║
  ███████╗█████╗  ██████╔╝███████║██████╔╝███████║
  ╚════██║██╔══╝  ██╔══██╗██╔══██║██╔═══╝ ██╔══██║
  ███████║███████╗██║  ██║██║  ██║██║     ██║  ██║
  ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝
```

**The Claude Code of penetration testing.**

[![Python](https://img.shields.io/badge/python-3.12%2B-blue?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Built with Claude](https://img.shields.io/badge/built%20with-Claude-orange?style=flat-square&logo=anthropic&logoColor=white)](https://anthropic.com)
[![uv](https://img.shields.io/badge/package%20manager-uv-purple?style=flat-square)](https://github.com/astral-sh/uv)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen?style=flat-square)](#testing)

---

Seraph is an AI pentest agent that runs in your terminal. Point it at a target, and it plans, scans, exploits, and escalates — asking your input between phases, streaming every tool call and finding in real time.

It learns from every engagement. The knowledge base (Qdrant + Neo4j + MITRE ATT&CK) continuously improves via LoRA fine-tuning on your retrieval feedback, so the tenth machine in a class is faster than the first.

```
  seraph> 10.10.10.3
  [*] Starting engagement against 10.10.10.3

    [recon / recon]
    ▸ nmap -sV -sC -oX - 10.10.10.3
    ✓ nmap (14.2s)

    [INFO    ]  SSH on port 22/tcp (OpenSSH 7.4)
    [INFO    ]  HTTP on port 80/tcp (Apache 2.4.6)
    [MEDIUM  ]  Samba 3.0.20 on port 445/tcp

  seraph> exploit the SMB service, it looks like CVE-2007-2447

    [exploit / exploit]
    ▸ metasploit exploit/multi/samba/usermap_script RHOST=10.10.10.3
    ✓ metasploit (8.7s)

    [CRITICAL]  Remote code execution — root shell obtained

  [+] Flags: d9e493...  (root)
```

---

## Install

**Requirements:** Python 3.12+, Docker, an [Anthropic API key](https://console.anthropic.com/)

```bash
pip install seraph-suite
```

Or with uv (recommended):

```bash
uv tool install seraph-suite
```

Then run the one-time setup:

```bash
seraph setup
```

Setup will:
- Create `.env` and prompt for your API key
- Pull and start the Docker services (Qdrant, Neo4j, Redis)
- Download and ingest the MITRE ATT&CK knowledge base

---

## Install from source (without PyPI)

Use this path if you want the latest unreleased code, want to contribute, or prefer not to install from PyPI.

**Requirements:** Python 3.12+, Git, Docker ([Docker Desktop](https://www.docker.com/products/docker-desktop/) on Windows), an [Anthropic API key](https://console.anthropic.com/)

### Linux

**With uv (recommended)**

```bash
# 1. Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env   # add uv to the current shell

# 2. Clone the repository
git clone https://github.com/aniolowie/seraph-suite.git
cd seraph-suite

# 3. Create a virtual environment and install all dependencies
uv sync

# 4. Run Seraph via uv
uv run seraph setup
uv run seraph
```

**With pip**

```bash
# 1. Clone the repository
git clone https://github.com/aniolowie/seraph-suite.git
cd seraph-suite

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install the package in editable mode
pip install -e .

# 4. Run the one-time setup
seraph setup
seraph
```

### Windows

Open **PowerShell** (or Windows Terminal).

**With uv (recommended)**

```powershell
# 1. Install uv if you don't have it
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# Restart PowerShell so uv is on your PATH

# 2. Clone the repository
git clone https://github.com/aniolowie/seraph-suite.git
cd seraph-suite

# 3. Create a virtual environment and install all dependencies
uv sync

# 4. Run Seraph via uv
uv run seraph setup
uv run seraph
```

**With pip**

```powershell
# 1. Clone the repository
git clone https://github.com/aniolowie/seraph-suite.git
cd seraph-suite

# 2. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install the package in editable mode
pip install -e .

# 4. Run the one-time setup
seraph setup
seraph
```

> **Windows note:** Make sure Docker Desktop is running before `seraph setup`. If you hit a script execution policy error, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` in PowerShell first.

---

## Usage

### Interactive REPL

```bash
seraph
```

Type a target IP or hostname to start. Type anything mid-engagement to steer the agent.

```
  seraph> 10.10.11.42
  seraph> focus on the web service, port 80
  seraph> findings
  seraph> status
  seraph> clear
  seraph> quit
```

### Quick-start against a target

```bash
seraph -t 10.10.10.3
```

### HTB benchmarking

```bash
# Single machine
seraph bench --machine Lame --timeout 3600

# All Easy machines with report
seraph bench --difficulty Easy --all --report --output reports/easy.md
```

### Knowledge base ingestion

```bash
# NVD CVE feed
seraph ingest nvd --year 2024

# MITRE ATT&CK (auto-downloads the STIX bundle)
seraph ingest mitre --download

# ExploitDB (clone the mirror first)
git clone https://gitlab.com/exploit-database/exploitdb ./data/exploitdb
seraph ingest exploitdb

# Your own CTF writeups (Markdown)
seraph ingest writeups ./data/writeups/

# Check ingestion stats
seraph ingest stats
```

### Sandbox isolation

Run all tool invocations inside isolated Docker containers (Manus-style):

```bash
SANDBOX_ENABLED=true seraph -t 10.10.10.3

# Pre-build the agent image
make sandbox-build
```

---

## How it works

```
 You
  │   type target / instruction
  ▼
 Orchestrator  ──── Claude Opus (planning)
  │
  ├── Recon Agent    → nmap, gobuster, curl
  ├── Exploit Agent  → metasploit, sqlmap, hydra
  ├── Privesc Agent  → linpeas, sudo checks, SUID
  ├── CTF Agent      → flag hunting, stego, web challenges
  └── Memorist       → logs which KB docs helped
         │
         ▼
  Knowledge Base
  ├── Qdrant   (BM25 + dense hybrid search, RRF fusion)
  ├── Neo4j    (MITRE ATT&CK graph, CVE → technique links)
  └── SQLite   (sessions, feedback, ingestion state)
         │
         ▼
  Self-learning loop
  └── feedback → hard negatives → triplets → LoRA fine-tune
```

**Retrieval pipeline** — every KB query runs:
1. BM25 sparse search (exact CVE IDs, tool names)
2. Dense semantic search (nomic-embed-text-v1.5, local)
3. RRF fusion
4. Neo4j graph traversal (expands CVE → linked techniques)
5. Cross-encoder reranking (bge-reranker-v2-m3, local)

All embeddings are computed locally — no API calls for embeddings.

---

## Configuration

All settings come from `.env`. Copy `.env.example` to get started.

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required** (unless using a local model). Your Anthropic key |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant vector store |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j graph store |
| `NEO4J_PASSWORD` | `seraph_secret` | Neo4j password |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker |
| `SANDBOX_ENABLED` | `false` | Docker tool isolation |
| `DENSE_EMBEDDING_MODEL` | `nomic-ai/nomic-embed-text-v1.5` | Local embedding model |
| `RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | Local reranker model |
| `LOG_LEVEL` | `INFO` | Log verbosity |
| `LOCAL_MODEL_ENABLED` | `false` | Use a local Ollama model instead of Anthropic |
| `LOCAL_MODEL_URL` | `http://localhost:11434` | Base URL of your Ollama server |
| `LOCAL_MODEL_NAME` | `qwen2.5-coder:8b` | Ollama model tag to use |

Services can be managed with:

```bash
make up      # start Qdrant + Neo4j + Redis
make down    # stop all services
make dev     # start with dev overrides
```

---

## Local model (Ollama)

Seraph can use a local model via [Ollama](https://ollama.com) instead of the Anthropic API.  This is useful for air-gapped environments or when you want to avoid API costs.

### 1. Install Ollama

**Linux / macOS**

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows** — download and run the installer from <https://ollama.com/download>.

### 2. Pull the model

```bash
ollama pull qwen2.5-coder:8b
```

Ollama must have the model available locally before Seraph starts.  If you see:

```
LLM decision failed: Local model HTTP 404: {"error":{"message":"model 'qwen2.5-coder:8b' not found",...}}
```

it means the model was not pulled.  Run the `ollama pull` command above to fix it.

You can use any model that Ollama supports — just change `LOCAL_MODEL_NAME` to match the tag you pulled (e.g. `llama3.1:8b`, `mistral:7b`, `deepseek-coder-v2:16b`).

### 3. Configure Seraph

Add the following lines to your `.env`:

```dotenv
LOCAL_MODEL_ENABLED=true
LOCAL_MODEL_URL=http://localhost:11434   # default; change if Ollama runs elsewhere
LOCAL_MODEL_NAME=qwen2.5-coder:8b       # must match the tag you pulled
```

When `LOCAL_MODEL_ENABLED=true`, the `ANTHROPIC_API_KEY` is not required.

### 4. Verify

Start Ollama (it may already be running as a system service after install):

```bash
ollama serve   # only needed if the daemon is not already running
```

Then launch Seraph as usual:

```bash
seraph
```

---

## Agents

| Agent | What it does | Tools |
|---|---|---|
| **Orchestrator** | Plans phases, dispatches sub-agents | — |
| **Recon** | Port scanning, service fingerprinting | nmap, gobuster, curl |
| **Exploit** | CVE matching, initial access | metasploit, sqlmap, hydra |
| **Privesc** | Privilege escalation | linpeas, custom checks |
| **CTF** | Flag hunting, stego, web challenges | gobuster, curl |
| **Memorist** | Logs KB feedback for self-learning | — |

When more than 20 tools are available, agents use RAG-based tool selection instead of passing all tools to the LLM.

---

## Self-learning

Every engagement makes Seraph better:

1. Memorist logs which retrieved documents the LLM cited vs ignored
2. Hard negatives mined from keyword-similar but semantically wrong retrievals
3. Triplets `(query, positive, negative)` accumulated in SQLite
4. LoRA adapter trained on `nomic-embed-text-v1.5` when enough triplets accumulate
5. Projection layer applied at query time — no need to re-embed the entire corpus

Retrieval quality improves measurably after ~50 engagements on similar machine classes.

---

## Testing

```bash
# Unit tests (no services needed)
make test-unit

# All tests + coverage report
make test

# Integration tests (requires services running)
make up && make test-integration

# Sandbox tests (requires Docker + agent image)
make sandbox-build && make sandbox-test
```

Coverage is enforced at 80%+.

---

## Dashboard

A FastAPI + React 18 dashboard is available:

```bash
make api-dev        # API at http://localhost:8000/docs
make dashboard-dev  # UI  at http://localhost:5173
```

---

## Contributing

Issues and PRs are welcome. Please open an issue before a large PR to align on direction.

1. Fork and create a branch
2. Type hints everywhere, Pydantic v2, async I/O, structlog
3. Write tests first — 80% coverage minimum
4. `make lint && make test-unit` before pushing

---

## License

MIT — see [LICENSE](LICENSE).

---

<sub>Built by [Maciej](https://github.com/Unohana) · Powered by [Anthropic Claude](https://anthropic.com)</sub>
