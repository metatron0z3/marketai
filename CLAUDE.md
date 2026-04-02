# MarketAI

Real-time market data platform with technical analysis. **NestJS + Python + Go + Angular + QuestDB**.

See README.md for full project overview and setup.

---

## Skills

Before starting any task, check `skills/` directory:
- **Multi-step/cross-service tasks** → Load `skills/orchestrator/SKILL.md` first
- **NestJS backend** → `skills/nestjs-backend/SKILL.md`
- **Python data/ML** → `skills/python-financial-api/SKILL.md` + `skills/ml-pipeline/SKILL.md`
- **Go streaming** → `skills/go-streaming/SKILL.md`
- **Angular frontend** → `skills/angular-frontend/SKILL.md`
- **System design** → `skills/system-design/SKILL.md`

---

## Commands

### Docker
```bash
# Start all services
docker-compose up --build

# Rebuild specific service
docker-compose build nestjs-backend

# View logs
docker-compose logs -f [service-name]
```

### NestJS Backend
```bash
cd backend-nest
npm install
npm run start:dev  # Development
npm run build      # Production
npm run test       # Run tests
```

### QuestDB Access
```bash
# Web console: http://localhost:9000
# PostgreSQL: psql -h localhost -p 8812 -U admin -d qdb
```

---

## Architecture

```
┌──────────────────┐
│   Angular (4200) │
└────────┬─────────┘
         │
    ┌────┴────┬────────┬──────────┐
    ▼         ▼        ▼          ▼
NestJS   Go Stream  Python    QuestDB
(3000)   (8082)    (8000)    (9000)
```

| Service | Port | Purpose |
|---------|------|---------|
| NestJS | 3000 | API gateway, market data, indicators |
| Python | 8000 | Data ingestion, feature engineering, ML |
| Go | 8082 | WebSocket streaming |
| QuestDB | 9000 | Time-series database |
| Frontend | 4200 | Web UI |

See `@docs/architecture.md` for detailed service breakdown.

---

## Conventions

- **NestJS modules**: One responsibility per module, DTOs for validation
- **Python**: Use polars for data loading, FastAPI for endpoints
- **API DTOs**: All inputs validated with Pydantic or NestJS decorators
- **Database**: Time-series queries use QuestDB's `SAMPLE BY` for aggregation
- **Frontend**: Angular services inject HTTP + state management via RxJS

---

## Non-obvious Constraints

- **QuestDB only**: Time-series data uses PostgreSQL wire protocol (port 8812)
- **Python-NestJS proxying**: NestJS proxies some Python endpoints (e.g., `/api/v1/ingest/`) to avoid service duplication
- **ML models**: Trained in Python, serialized as TorchScript/ONNX, served via FastAPI
- **Skills are required**: Every task should load the relevant skill file(s) — they contain implementation patterns

---

## References

- **Full architecture details** → `@docs/architecture.md`
- **API reference** → `@docs/api-routes.md`
- **Database schema** → `@docs/database.md`
- **Environment setup** → `@docs/environment.md`
- **Data ingestion flow** → `@docs/data-ingestion.md`
