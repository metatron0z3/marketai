# Development Workflow

## Quick Start

### 1. Start All Services

```bash
docker-compose up --build
```

Wait 30-40 seconds for services to initialize.

### 2. Verify Services

- **Frontend**: http://localhost:4200
- **NestJS API**: http://localhost:3000/health
- **Swagger Docs**: http://localhost:3000/api/docs
- **QuestDB Console**: http://localhost:9000
- **Python Service** (internal): http://localhost:8000 (not exposed to browser)

### 3. Load Sample Data

1. Download `.dbn.zst` from Databento
2. Go to Frontend → Ingest page
3. Upload file
4. Monitor job status

## Backend Development

### NestJS (Port 3000)

```bash
cd backend-nest

# Install dependencies
npm install

# Run in dev mode (auto-reload)
npm run start:dev

# Build for production
npm run build

# Run tests
npm run test
```

**Useful Commands**:
- Lint: `npm run lint`
- Format: `npm run format`
- Generate Swagger docs: `npm run build` (automatic)

**Key Files**:
- `src/app.module.ts` — Module registration
- `src/modules/*/` — Feature modules (instruments, market-data, indicators)
- `src/database/questdb.service.ts` — DB connection pool

### Python Service (Port 8000)

```bash
cd python-service

# Install dependencies
pip install -r requirements.txt

# Run in dev mode
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest

# Format/lint
black app/ && ruff check app/
```

**Key Files**:
- `app/main.py` — FastAPI entry point
- `app/api/v1/endpoints/` — Route handlers
- `app/services/` — Business logic (indicators, ingest)
- `app/core/db.py` — QuestDB connection

## Frontend Development

### Angular (Port 4200)

```bash
cd frontend

# Install dependencies
npm install

# Run dev server
npm start  # or ng serve

# Build for production
npm run build

# Run tests
npm test

# Lint
ng lint
```

**Key Files**:
- `src/app/pages/` — Page components
- `src/app/components/chart/` — Chart component (lightweight-charts)
- `src/app/core/services/api.service.ts` — HTTP client

## Debugging

### Docker Logs

```bash
# All services
docker-compose logs -f

# Single service
docker-compose logs -f nestjs-backend
docker-compose logs -f python-service
docker-compose logs -f questdb

# Last 50 lines
docker-compose logs --tail=50 python-service
```

### Shell Access

```bash
# Enter container
docker-compose exec nestjs-backend sh
docker-compose exec python-service bash
docker-compose exec questdb bash
```

### QuestDB Debugging

```bash
# Connect via psql
psql -h localhost -p 8812 -U admin -d qdb

# Query trades_data
SELECT COUNT(*) FROM trades_data;
SELECT DISTINCT instrument_id FROM trades_data;
```

## Testing

### NestJS Tests

```bash
cd backend-nest
npm run test              # Run all tests
npm run test:watch       # Watch mode
npm run test:cov         # Coverage report
```

### Python Tests

```bash
cd python-service
pytest
pytest -v               # Verbose
pytest --cov app/       # Coverage
```

## Code Style

### NestJS

- **Framework**: NestJS (TypeScript)
- **Formatting**: Prettier (auto-format in pre-commit hooks)
- **Linting**: ESLint
- **DTOs**: All inputs validated with NestJS decorators

### Python

- **Formatter**: Black
- **Linter**: Ruff
- **Type checking**: Mypy (optional, recommended)

## Git Workflow

1. Create feature branch: `git checkout -b feature/my-feature`
2. Make changes, test locally: `docker-compose up --build`
3. Commit with conventional message: `git commit -m "feat: description"`
4. Push: `git push origin feature/my-feature`
5. Open PR on GitHub

See README.md for branch naming conventions.

## Common Tasks

### Add a New API Endpoint (NestJS)

1. Create controller: `src/modules/my-module/my-module.controller.ts`
2. Create service: `src/modules/my-module/my-module.service.ts`
3. Create DTO: `src/modules/my-module/dto/my-dto.ts`
4. Register in `my-module.module.ts`
5. Import module in `app.module.ts`

### Add a New Indicator (Python)

1. Implement calculation in `app/services/indicators.py`
2. Expose endpoint in `app/api/v1/endpoints/indicators.py`
3. Register endpoint in `app/api/v1/api.py`
4. Test locally
5. Proxy from NestJS if exposing to frontend

### Update Database Schema

1. **Never modify production schema directly**
2. Use QuestDB DDL in `python-service/app/core/db.py`
3. Test migrations in Docker environment
4. Document changes in `@docs/database.md`

## Resources

- **NestJS Docs**: https://docs.nestjs.com/
- **QuestDB Docs**: https://questdb.io/docs/
- **Databento API**: https://databento.com/docs/
- **Angular Docs**: https://angular.io/docs
