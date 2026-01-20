# GEMINI.md - Refactor Master Plan

## Project Context
This project is currently a Python-based data pipeline using QuestDB and Streamlit.
**Current Objective:** Perform a major architectural refactor to decouple the frontend and backend, moving to a production-grade stack (FastAPI + Angular) while retaining the data ingestion and storage logic.

**Branch Strategy:** All changes described below are taking place in a specific feature branch.

---

## 1. Target Architecture

The application is migrating from a monolithic script structure to a 3-tier architecture:

### Tier 1: Data & Storage (Existing - Keep Intact)
- **Database:** QuestDB (Time-series database).
- **Ingestion:** Python script (`src/ingest_cli.py`) using `databento`.
- **Infrastructure:** Docker & Docker Compose.
- **Constraint:** The existing QuestDB setup and Docker network configuration must remain intact, though the `docker-compose.yml` will need updates to swap Streamlit for the new services.

### Tier 2: API Layer (New - FastAPI)
- **Framework:** Python FastAPI.
- **Responsibilities:**
  - Handle persistent database connections to QuestDB.
  - Expose RESTful endpoints for frontend consumption.
  - Type validation (Pydantic).
  - *Future consideration:* Structure the API to allow for a future ML/Feature Engineering pipeline (separation of concerns).

### Tier 3: Frontend Layer (New - Angular)
- **Framework:** Angular (Latest stable).
- **Design Philosophy:** Extensible, modular dashboard.
- **Charting Goal:** "Pro-level" financial charting (resembling TradingView or ThinkorSwim).
  - *Note:* We will likely leverage libraries compatible with Angular that offer high-performance time-series rendering (e.g., Lightweight Charts, Apache ECharts, or Highcharts).
- **UX:** Dynamic sidebars, multi-page routing, and a containerized main view for different chart types.

---

## 2. Agent Workflow Protocols (Strict)

When helping me with this refactor, you **must** adhere to these rules:

1.  **Component Check-in:** Before generating complex Angular components, **stop and ask me** about the design and requirements. Do not assume the structure. I want to manage the growth of the frontend to prevent "spaghetti code."
2.  **Extensibility First:** Write code that assumes new pages and new chart types will be added later. Avoid hard-coding logic that binds the app to a single dataset or view.
3.  **Legacy Cleanup:** As we successfully migrate features (e.g., moving a chart from Streamlit to Angular), you may suggest deleting the old Python files. **Ask for confirmation** before executing deletions.
4.  **Docker Stability:** Ensure the application remains runnable via `docker-compose` throughout the process.

---

## 3. Refactoring Roadmap

### Phase 1: Backend Foundation (FastAPI)
- [ ] Create a `backend/` directory.
- [ ] Initialize a FastAPI app.
- [ ] Implement a database connector (using `psycopg2` or `requests` depending on QuestDB interface preference) that replicates the logic currently in `src/ingest_cli.py`.
- [ ] Create an initial endpoint to fetch OHLC/Trade data.

### Phase 2: Frontend Foundation (Angular)
- [ ] Create a `frontend/` directory.
- [ ] Initialize a new Angular application.
- [ ] Update `docker-compose.yml` to include the Frontend (Node/Nginx) and Backend (Uvicorn) services, removing the Streamlit service.
- [ ] Establish the basic layout: Sidebar (Navigation) + Main Content Area (Router Outlet).

### Phase 3: Charting & Visualization
- [ ] Select and install a financial charting library (Target: TradingView look & feel).
- [ ] Connect Angular service to FastAPI endpoint.
- [ ] Render the first interactive chart (replicating the `market_view_day.py` functionality).

### Phase 4: Expansion & Cleanup
- [ ] Refactor sidebars to be dynamic based on the active view.
- [ ] Verify all Streamlit functionality is ported.
- [ ] Delete `src/market_view_day.py` and remove Streamlit dependencies.

---

## 4. Legacy Documentation (Reference Only)

*The following describes the OLD architecture. Use this only to understand what logic needs to be ported.*

- **Ingestion:** `src/ingest_cli.py` (Keep this logic, but API needs to read what this writes).
- **Old Frontend:** `src/market_view_day.py` (Streamlit).
- **Old Env:** `requirements.streamlit.txt`.

### Database Schema (Reference)
The schema is defined in `create_table_if_not_exists` in `src/ingest_cli.py`. The API must respect this schema.