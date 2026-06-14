# Environment Variables

## NestJS Backend

```env
NODE_ENV=development
PORT=3000
QUESTDB_HOST=questdb
QUESTDB_PORT=8812
QUESTDB_USER=admin
QUESTDB_PASSWORD=quest
QUESTDB_DATABASE=qdb
PYTHON_SERVICE_URL=http://python-service:8000
```

### Variable Descriptions

- **NODE_ENV**: `development` or `production`
- **PORT**: API server port
- **QUESTDB_HOST**: QuestDB hostname (docker-compose: `questdb`)
- **QUESTDB_PORT**: PostgreSQL wire protocol port (not HTTP 9000)
- **QUESTDB_USER**: Default admin user
- **QUESTDB_PASSWORD**: Default password
- **QUESTDB_DATABASE**: Database name
- **PYTHON_SERVICE_URL**: Python service base URL (for proxying)

## Python Service

```env
QUESTDB_HOST=questdb
QUESTDB_PORT=9000
MASSIVE_API_KEY=your_massive_api_key_here
MASSIVE_BASE_URL=https://api.massive.com
```

### Variable Descriptions

- **QUESTDB_HOST**: QuestDB hostname
- **QUESTDB_PORT**: HTTP API port (not PostgreSQL 8812)
- **MASSIVE_API_KEY**: API key for Massive REST data feed. Required to use `POST /api/v1/options/ingest/massive`. Never log or commit this value.
- **MASSIVE_BASE_URL**: Base URL for the Massive API (default: `https://api.massive.com`). Override only in testing or when pointing at a proxy.

## Local Development

Create `.env.local` files in each service directory to override defaults:

```bash
# backend-nest/.env.local
NODE_ENV=development
QUESTDB_HOST=localhost
QUESTDB_PORT=8812
```

Never commit `.env.local` or `.env` files with secrets.

## Docker Compose

Services in `docker-compose.yml` inherit these environment variables automatically — no need to set them manually unless running services locally (outside Docker).
