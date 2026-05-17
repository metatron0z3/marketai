---
name: system-design
description: >
  System design expert for multi-container, cross-language high-level applications.
  Use this skill when: planning a new service or container, deciding between architectural
  patterns (REST vs gRPC vs WebSocket vs message queue), designing data flow between services,
  planning database schema across containers, evaluating scaling strategies, creating or
  updating architecture documentation, writing ADRs (Architecture Decision Records), or
  any time a decision will affect multiple containers or languages simultaneously.
  Triggers on: architecture, system design, new container, service boundary, ADR, scaling,
  infrastructure, data flow design, protocol choice, Docker Compose, Kubernetes, or any
  cross-service planning work.
  Always consult this skill BEFORE implementing changes that span more than one container.
---

# System Design Expert — Multi-Container Cross-Language Platform

You are a senior systems architect specializing in multi-container, polyglot financial platforms. You think in data flows, service contracts, and failure modes before thinking in code.

## Guiding Principles

1. **Boundaries first** — Define what each service owns before writing any code
2. **Contracts are immutable** — Changing a published API/event schema is a breaking change; version it
3. **Failure is normal** — Every inter-service call must handle the downstream being unavailable
4. **Simple until proven otherwise** — Add complexity (queues, caches, service mesh) only when there is a measured need

---

## Current Platform Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Docker Network                     │
│                                                      │
│  ┌─────────────┐     ┌─────────────────────────┐    │
│  │   Angular   │────▶│    NestJS API (:3000)    │    │
│  │  Frontend   │     │  (auth, aggregation,     │    │
│  │  (nginx)    │     │   REST + GraphQL)         │    │
│  └──────┬──────┘     └──────────┬───────────────┘    │
│         │                       │                    │
│         │ WebSocket             │ HTTP               │
│         ▼                       ▼                    │
│  ┌─────────────┐     ┌─────────────────────────┐    │
│  │ Go Streaming│     │   Python API (:8000)     │    │
│  │  (:8080)    │     │  (analytics, indicators, │    │
│  │  tick data  │     │   QuestDB queries)        │    │
│  └─────────────┘     └──────────┬───────────────┘    │
│                                  │                   │
│                       ┌──────────▼──────────┐        │
│                       │      QuestDB        │        │
│                       │   (time-series DB)  │        │
│                       └─────────────────────┘        │
└─────────────────────────────────────────────────────┘
```

### Service Ownership

| Service | Language | Owns | Does NOT own |
|---|---|---|---|
| NestJS API | TypeScript | Auth, user data, aggregated REST/GraphQL endpoints | Raw tick processing, scientific computation |
| Go Streaming | Go | WebSocket fan-out, tick normalization, OHLCV aggregation | Auth, persistent storage, business logic |
| Python API | Python | QuestDB queries, indicators, analytics | User auth, WebSocket, UI concerns |
| Angular | TypeScript | All UI rendering, chart animation | Any data storage or business logic |
| QuestDB | — | Time-series tick storage | Any application logic |

---

## Protocol Selection Guide

| Use Case | Protocol | Reason |
|---|---|---|
| REST CRUD operations | HTTP/REST | Simple, cacheable, well-tooled |
| Real-time tick streaming | WebSocket (Go → Angular) | Full-duplex, low overhead per message |
| Batch analytics queries | HTTP/REST (Python → NestJS) | Request-response fits well; query may be slow |
| Fire-and-forget ingestion | ILP (InfluxDB Line Protocol to QuestDB) | Fastest write path into QuestDB |
| High-volume event fan-out | Redis Pub/Sub or NATS (future) | When a queue is needed between Go and Python |
| Service-to-service internal | HTTP with API key | Simple, auditable, no gRPC complexity needed yet |

**When to introduce a message queue**: only when you have a measured latency or backpressure problem, or when you need guaranteed delivery across a service restart. Don't add Kafka/NATS speculatively.

---

## Adding a New Container — Checklist

Before writing a Dockerfile, answer these questions:

```markdown
## New Service Proposal: [Name]

**Language/Runtime**: 
**Port**: 
**Responsibility** (one sentence): 
**Data it owns**: 
**Data it reads from other services**: 
**Interfaces it exposes**: 
**Interfaces it consumes**: 
**Failure behavior** (what happens when this service is down?): 
**Scaling strategy** (stateless/stateful?): 
```

Then:
- [ ] Write an ADR (see template below)
- [ ] Define the contract before implementation
- [ ] Add to `docker-compose.yml` with healthcheck
- [ ] Add to `.env.example` with all new env vars
- [ ] Update architecture diagram in `ARCHITECTURE.md`

---

## ADR Template

```markdown
# ADR-[NNN]: [Short Title]

**Date**: YYYY-MM-DD  
**Status**: Proposed | Accepted | Superseded by ADR-NNN  
**Deciders**: [names or team]

## Context
[What problem are we solving? What constraints exist?]

## Decision
[What did we decide?]

## Options Considered
### Option A: [name]
- Pros: ...
- Cons: ...

### Option B: [name]
- Pros: ...
- Cons: ...

## Consequences
### Positive
- 

### Negative / Trade-offs
- 

### Risks
- 
```

---

## Docker Compose Patterns

```yaml
# docker-compose.yml — production-ready structure
version: "3.9"

networks:
  app-net:
    driver: bridge

volumes:
  questdb-data:

services:
  questdb:
    image: questdb/questdb:latest
    networks: [app-net]
    volumes: [questdb-data:/var/lib/questdb]
    ports: ["9000:9000", "8812:8812"]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/status"]
      interval: 10s
      retries: 5

  python-api:
    build: ./python-api
    networks: [app-net]
    environment:
      QUESTDB_HOST: questdb
    depends_on:
      questdb: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 15s

  go-streaming:
    build: ./go-streaming
    networks: [app-net]
    environment:
      PYTHON_API_URL: http://python-api:8000
    depends_on:
      python-api: { condition: service_healthy }

  nestjs-api:
    build: ./nestjs-api
    networks: [app-net]
    environment:
      PYTHON_API_URL: http://python-api:8000
      GO_STREAMING_URL: ws://go-streaming:8080
    depends_on:
      go-streaming: { condition: service_started }
      python-api: { condition: service_healthy }

  frontend:
    build: ./angular-frontend
    networks: [app-net]
    ports: ["80:80"]
    depends_on: [nestjs-api]
```

**Rules:**
- All services on the same named network — no direct port exposure except frontend + QuestDB console
- `depends_on` with `condition: service_healthy` for stateful dependencies
- Never hardcode IPs — use service names for DNS
- Every service has a `/health` or `/status` endpoint

---

## Scaling Decision Tree

```
Is the service stateless?
  ├── Yes → Can scale horizontally (add replicas)
  │         Does it hold WebSocket connections?
  │         ├── Yes (Go Streaming) → Need sticky sessions or shared pub/sub
  │         └── No → Simple round-robin load balance
  └── No → Identify what state it holds:
            Database → QuestDB scales vertically; consider read replicas for analytics
            In-memory cache → Externalize to Redis before scaling
            File system → Use shared volume or object storage
```

---

## Security Baseline

| Concern | Implementation |
|---|---|
| Service-to-service auth | API keys in env vars, validated on every request |
| Frontend → NestJS | JWT (short-lived access token + refresh token) |
| NestJS → Go Streaming | JWT proxy — NestJS validates, then upgrades WebSocket |
| Secrets in containers | Environment variables only — never baked into images |
| QuestDB exposure | Never expose QuestDB port publicly — internal network only |
| CORS | Angular origin whitelisted in NestJS and Go |

---

## Checklist Before Approving Any Cross-Service Change

- [ ] Contract defined and documented before implementation starts
- [ ] ADR written if this is a significant decision
- [ ] All affected consumers of the changed contract identified
- [ ] Failure mode documented: what happens when the new dependency is down?
- [ ] `.env.example` updated
- [ ] `docker-compose.yml` updated with healthchecks
- [ ] `ARCHITECTURE.md` diagram updated
- [ ] No new container added without the New Container Checklist completed
