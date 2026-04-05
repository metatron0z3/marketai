---
name: nestjs-backend
description: >
  NestJS and TypeScript expert for a multi-container financial platform backend.
  Use this skill for ALL NestJS work: creating modules, controllers, services, guards,
  interceptors, pipes, DTOs, database migrations, message queues, WebSocket gateways,
  Docker configuration, environment management, and multi-container backend architecture.
  Triggers on: NestJS, TypeScript backend, REST API, GraphQL, microservices, Bull queues,
  TypeORM, Prisma, authentication/JWT, backend testing, or any backend container work.
  Always load this skill before writing any NestJS code — it contains critical conventions
  for this codebase.
---

# NestJS / TypeScript Backend Expert

You are an expert NestJS engineer building an extensible, multi-container financial platform backend. You write production-grade, well-tested TypeScript that is easy to extend.

## Stack
- **Framework**: NestJS (latest stable)
- **Language**: TypeScript (strict mode always on)
- **ORM**: TypeORM (primary) or Prisma (if user specifies)
- **Queue**: BullMQ
- **Auth**: JWT + Passport.js
- **Testing**: Jest + Supertest
- **Container**: Docker + Docker Compose

---

## Module Architecture

Every feature lives in its own module. The structure is non-negotiable:

```
src/
├── app.module.ts              # Root module — imports only feature modules
├── common/
│   ├── decorators/
│   ├── filters/               # Global exception filters
│   ├── guards/
│   ├── interceptors/
│   ├── pipes/
│   └── dto/                   # Shared DTOs
├── config/
│   └── configuration.ts       # Typed config via @nestjs/config
├── database/
│   └── migrations/
└── features/
    └── [feature-name]/
        ├── [feature].module.ts
        ├── [feature].controller.ts
        ├── [feature].service.ts
        ├── [feature].repository.ts   # Optional — for complex queries
        ├── dto/
        │   ├── create-[feature].dto.ts
        │   └── [feature]-response.dto.ts
        ├── entities/
        │   └── [feature].entity.ts
        └── [feature].service.spec.ts
```

### Module Creation Checklist
- [ ] Module file imports all needed providers
- [ ] Module only exports what other modules need
- [ ] Controller uses `@ApiTags` + `@ApiOperation` for Swagger
- [ ] Service does not import other feature services directly — use events or shared services
- [ ] All env vars accessed via `ConfigService`, never `process.env` directly

---

## TypeScript Conventions

```typescript
// ✅ Always use strict DTOs with class-validator
import { IsString, IsNumber, IsOptional, Min } from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class CreateOrderDto {
  @ApiProperty({ description: 'Ticker symbol', example: 'AAPL' })
  @IsString()
  ticker: string;

  @ApiProperty({ example: 100 })
  @IsNumber()
  @Min(1)
  quantity: number;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  notes?: string;
}

// ✅ Typed config — never process.env raw
export default () => ({
  database: {
    host: process.env.DB_HOST,
    port: parseInt(process.env.DB_PORT ?? '5432', 10),
  },
  jwt: {
    secret: process.env.JWT_SECRET,
    expiresIn: process.env.JWT_EXPIRES_IN ?? '1d',
  },
});
```

---

## Inter-Service Communication

### With Python API
- Python exposes OpenAPI spec → generate TypeScript client with `openapi-typescript`
- Use `HttpModule` + typed axios client in NestJS service layer
- Always handle errors with a dedicated `PythonApiException`

### With Go Streaming
- NestJS acts as **auth gateway** — validates JWT, then proxies WebSocket upgrade to Go
- Share event type definitions in `shared-types/` package
- NestJS **never** processes raw tick data — that's Go's domain

### Shared Types Package
```
shared-types/
├── package.json               # name: "@yourapp/shared-types"
├── src/
│   ├── events/
│   │   └── tick.event.ts      # WebSocket message shapes
│   └── api/
│       └── market-data.dto.ts # Shared API shapes
└── index.ts
```

---

## Database Patterns

### Entity Conventions
```typescript
import { Entity, Column, PrimaryGeneratedColumn, CreateDateColumn, Index } from 'typeorm';

@Entity('orders')
@Index(['ticker', 'createdAt'])   // Always add indexes on filter/sort columns
export class OrderEntity {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ length: 10 })
  ticker: string;

  @CreateDateColumn()
  createdAt: Date;
}
```

### Migration Workflow
```bash
# Generate after entity changes
npm run typeorm migration:generate -- -n MigrationName

# Never edit generated migrations — write a new one instead
# Always test rollback: npm run typeorm migration:revert
```

---

## Docker / Container Config

```dockerfile
# Dockerfile (multi-stage)
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
EXPOSE 3000
CMD ["node", "dist/main"]
```

```yaml
# docker-compose.yml excerpt
nestjs-api:
  build: ./nestjs-api
  environment:
    - NODE_ENV=production
    - DB_HOST=postgres
  depends_on:
    - postgres
    - redis
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

---

## Testing Standards

- **Unit tests**: every service method, mock all dependencies with `jest.fn()`
- **Integration tests**: every controller endpoint via Supertest
- **Coverage target**: 80% minimum on services
- Use `Test.createTestingModule()` — never instantiate classes directly

```typescript
describe('OrderService', () => {
  let service: OrderService;
  let repo: jest.Mocked<Repository<OrderEntity>>;

  beforeEach(async () => {
    const module = await Test.createTestingModule({
      providers: [
        OrderService,
        { provide: getRepositoryToken(OrderEntity), useValue: { findOne: jest.fn(), save: jest.fn() } },
      ],
    }).compile();
    service = module.get(OrderService);
    repo = module.get(getRepositoryToken(OrderEntity));
  });

  it('should throw if order not found', async () => {
    repo.findOne.mockResolvedValue(null);
    await expect(service.findById('bad-id')).rejects.toThrow(NotFoundException);
  });
});
```

---

## Checklist Before Completing Any Task

- [ ] Strict TypeScript — no `any`
- [ ] DTOs validated with `class-validator`
- [ ] Swagger decorators on all endpoints
- [ ] Config accessed via `ConfigService`
- [ ] Module boundaries respected — no cross-feature direct imports
- [ ] Unit test written for new service methods
- [ ] Migration created for any schema change
- [ ] `.env.example` updated for any new env vars
- [ ] Docker healthcheck present if new container
