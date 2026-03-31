# Dashboard — Seraph Suite UI

## Overview

The Seraph Suite dashboard is a React 18 single-page application that provides real-time visibility into engagements, benchmarks, the knowledge base, and the self-learning loop. It communicates with the FastAPI backend via REST and WebSocket.

---

## Architecture

```
dashboard/
├── src/
│   ├── api/
│   │   ├── client.ts        # fetch wrapper + WebSocket factory
│   │   └── types.ts         # TypeScript interfaces mirroring backend schemas
│   ├── hooks/               # TanStack Query hooks per resource
│   ├── components/          # Shared UI + feature components
│   ├── pages/               # Route-level page components
│   ├── test/setup.ts        # Vitest + jsdom setup (MockWebSocket, fetch mock)
│   └── App.tsx              # React Router v6 routes (lazy-loaded)
├── vite.config.ts           # Vite + vitest config, /api proxy to :8000
├── nginx.conf               # nginx config for production container
└── Dockerfile               # Multi-stage: node:20-alpine build → nginx:alpine
```

### Tech stack

| Layer | Library |
|---|---|
| Framework | React 18 |
| Build | Vite 5 |
| Routing | React Router v6 |
| Data fetching | TanStack Query v5 |
| Charts | Recharts 2 |
| Testing | Vitest 2 + React Testing Library |
| Language | TypeScript (strict) |

---

## Pages

| Route | Page | Description |
|---|---|---|
| `/` | `DashboardPage` | Overview: active engagements, recent benchmarks, KB status, learning progress |
| `/engagements/:id` | `EngagementDetailPage` | Live engagement feed via WebSocket, flags, findings |
| `/benchmarks` | `BenchmarksPage` | Benchmark run history, pass/fail per machine |
| `/knowledge` | `KnowledgePage` | Collection stats, ingestion source status |
| `/learning` | `LearningPage` | Feedback records, triplets, training history chart |
| `/machines` | `MachinesPage` | Machine registry CRUD |
| `/writeups` | `WriteupsPage` | Markdown writeup upload form |

---

## Development

### Prerequisites

- Node.js 20+
- npm 10+
- FastAPI backend running on `localhost:8000`

### Start dev server

```bash
make dashboard-dev
# OR
cd dashboard && npm run dev
```

The Vite dev server runs on `http://localhost:5173` and proxies `/api/*` to `http://localhost:8000`.

### Run tests

```bash
make dashboard-test
# OR
cd dashboard && npm test
```

### Build for production

```bash
make dashboard-build
# OR
cd dashboard && npm run build
```

Output is in `dashboard/dist/`.

---

## Production deployment

### Docker Compose (recommended)

The `docker-compose.yml` defines an `api` service and a `dashboard` service. Both are started with:

```bash
make up
```

The dashboard container serves the built React app on port 80 and proxies `/api/*` to the `api` service.

### Manual

```bash
cd dashboard
npm run build
# Serve dashboard/dist/ with any static file server + reverse proxy for /api/
```

---

## API proxy

In development Vite proxies `/api/*` to `http://localhost:8000`.

In production the nginx container proxies `/api/*` to `http://api:8000` (Docker service name). WebSocket upgrades (`/api/engagements/:id/ws`) are supported via `Upgrade`/`Connection` header forwarding.

---

## Environment variables

No environment variables are needed for the dashboard itself — all API calls go through `/api/` which is proxied by nginx or Vite. Backend environment variables are documented in `.env.example`.

---

## WebSocket

Active engagement feeds use WebSocket connections. The client connects to `/api/engagements/{id}/ws` which is handled by the FastAPI backend. The `createEngagementWs()` function in `src/api/client.ts` wraps the native `WebSocket` API.

In tests a `MockWebSocket` global in `src/test/setup.ts` replaces `window.WebSocket` to avoid real network connections.

---

## Testing strategy

- **Unit tests** in `src/__tests__/` cover individual components and pages.
- `global.fetch` is mocked in `setup.ts`; each test overrides it as needed.
- `MockWebSocket` is injected globally so WebSocket-dependent components render without network.
- TanStack Query clients are created with `retry: false` and `staleTime: Infinity` to prevent background refetches during tests.
