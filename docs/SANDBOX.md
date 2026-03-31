# Sandbox Architecture

Seraph Suite Phase 5 adds Manus-style per-agent Docker container isolation.
Each agent executes its tools inside a dedicated container with scoped
networking, CPU/memory limits, and a restricted toolset.

---

## Overview

```
  ┌─────────────────────────────────────────┐
  │  LangGraph orchestrator (host process)   │
  │                                          │
  │  BaseAgent._execute_tool()               │
  │       │                                  │
  │       ├── sandbox_executor is None?      │
  │       │   └── tool.execute() directly    │
  │       │                                  │
  │       └── SandboxExecutor present?       │
  │           └── docker exec → container   │
  └─────────────────────────────────────────┘
           │
           ▼
  ┌─────────────────────────────────────────┐
  │  ContainerPool (asyncio.Queue)           │
  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ │
  │  │ seraph-  │ │ seraph-  │ │ seraph-  │ │
  │  │ agent:0  │ │ agent:1  │ │ agent:2  │ │
  │  └──────────┘ └──────────┘ └──────────┘ │
  └─────────────────────────────────────────┘
           │
  seraph-agent-net (Docker bridge)
           │
      [target IP]
```

---

## Components

| Module | Class | Responsibility |
|---|---|---|
| `sandbox/models.py` | `ContainerSpec`, `ContainerInfo`, `ExecResult`, `PooledContainer` | Typed data models |
| `sandbox/network.py` | `SandboxNetworkManager` | Create/remove per-engagement bridge networks |
| `sandbox/manager.py` | `ContainerManager` | Container lifecycle: create/start/stop/remove/health-check |
| `sandbox/executor.py` | `SandboxExecutor` | `docker exec` with `asyncio.wait_for` timeout |
| `sandbox/pool.py` | `ContainerPool` | Fixed pool of warm containers; lease/release with auto-replacement |

### Strategy pattern

`SandboxExecutor` is injected into `BaseAgent` as an optional parameter.
When `None` (default), `_execute_tool` runs the tool locally.
When set, `_execute_tool` calls `tool.to_sandbox_command()` → `docker exec`.
Zero code change required in individual agent or tool subclasses.

---

## Building the agent image

```bash
make sandbox-build
# Equivalent: docker build -t seraph-agent:latest -f src/seraph/sandbox/Dockerfile.agent .
```

The Dockerfile uses `kalilinux/kali-rolling` as base and installs:
- Recon: `nmap`, `dnsrecon`, `amass`, `gobuster`, `ffuf`
- Web: `nikto`, `sqlmap`, `wfuzz`
- Exploitation: `metasploit-framework`, `exploitdb`
- Privesc: `linpeas`

---

## Configuration

All sandbox settings live in `.env` / `config.py` under the `sandbox_*` prefix:

| Variable | Default | Description |
|---|---|---|
| `SANDBOX_ENABLED` | `false` | Enable Docker sandbox routing |
| `SANDBOX_IMAGE` | `seraph-agent:latest` | Docker image to use |
| `SANDBOX_CPU_LIMIT` | `1.0` | CPU cores per container |
| `SANDBOX_MEMORY_LIMIT_MB` | `512` | MiB RAM per container |
| `SANDBOX_POOL_SIZE` | `3` | Warm container count |
| `SANDBOX_POOL_TIMEOUT_SECONDS` | `30` | Lease wait timeout |
| `SANDBOX_CONTAINER_TIMEOUT` | `3600` | Max container lifetime |
| `SANDBOX_DATA_VOLUME` | `./data` | Host path mounted at `/data` |
| `SANDBOX_NETWORK_NAME` | `seraph-agent-net` | Docker bridge network |

Set `SANDBOX_ENABLED=false` (the default) for local development — Docker is
not required and all tools run in-process.

---

## Running tests

```bash
# Unit tests (no Docker required)
make test-unit

# Integration tests (requires Docker daemon + seraph-agent image)
make sandbox-test
```

Integration tests are marked `@pytest.mark.integration` and skipped
automatically when Docker is unavailable.

---

## Cleaning up

```bash
make sandbox-clean
# Equivalent: docker ps -aq --filter "label=seraph.managed=true" | xargs -r docker rm -f
```

All Seraph-managed containers carry the `seraph.managed=true` Docker label,
making bulk cleanup safe and targeted.
