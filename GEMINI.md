# GEMINI.md - Go Streaming Service & Animated Chart

## Project Objective
This document outlines the plan to introduce a new real-time data streaming service written in Go and a corresponding animated candlestick chart on the Angular frontend. This will provide a "live" market view, simulating the formation of 5-minute candlestick data.

**Branch Strategy:** All changes will be developed in the current feature branch.

---

## 1. Target Architecture

### Tier 1: Data Streaming Service (New - Go)
-   **Language:** Go
-   **Responsibilities:**
    -   Read 5-minute OHLCV data.
        -   **Phase 1 Source:** Read from a static CSV file (`backend/app/models/static_data/questdb-query-1769038517286.csv`).
        -   **Phase 2 Source:** Connect directly to the QuestDB container and query the data.
    -   Expose a WebSocket endpoint for the frontend.
    -   Simulate real-time candle formation by streaming data points at 2-second intervals. For each 5-minute candle from the source, the service will generate and send intermediate price updates to animate the candle's construction on the frontend.
-   **Infrastructure:** The service will run in a new Docker container named `streaming`.

### Tier 2: Frontend Layer (Angular)
-   **Framework:** Angular
-   **New Page:** A new route and component will be created to host the animated chart (`/animated-chart`).
-   **Charting Goal:** Display a candlestick chart that animates in real-time based on the data streamed from the Go service. The chart should cover a 5-day trading week (9:30 am - 4:00 pm).
-   **Connectivity:** The frontend will use a service to connect to the Go application's WebSocket endpoint.

---

## 2. Refactoring Roadmap

### Phase 1: Go Service Foundation & Mock Data Streaming
-   [ ] Create a `streaming/` directory for the Go application.
-   [ ] Initialize a Go module.
-   [ ] Implement a basic HTTP/WebSocket server in `streaming/main.go`.
-   [ ] Create a `streaming/Dockerfile` to build and run the Go application.
-   [ ] Implement a CSV reader to parse the data from `backend/app/models/static_data/questdb-query-1769038517286.csv`.
-   [ ] Develop the core streaming logic: For each 5-minute data row, simulate and stream interpolated price ticks every 2 seconds over the WebSocket.
-   [ ] Update `docker-compose.yml` to add the new `streaming` service.

### Phase 2: Frontend Animated Chart
-   [ ] Generate a new Angular component for the animated chart (`ng generate component animated-chart`).
-   [ ] Add a new route (`/animated-chart`) in `app.routes.ts` pointing to the new component.
-   [ ] Select and integrate a suitable charting library that supports real-time updates (e.g., Lightweight Charts, ECharts).
-   [ ] Implement a WebSocket service in Angular to connect to the Go streamer.
-   [ ] Develop the component logic to receive streaming data and update the chart, creating the animation effect for each candle.
-   [ ] Ensure the chart correctly displays the default range (5-day trading week, 9:30 am - 4:00 pm).

### Phase 3: QuestDB Integration & Cleanup
-   [ ] Modify the Go service to connect to the QuestDB database instead of reading from the CSV file.
-   [ ] Implement the SQL query in the Go service to fetch the required OHLCV data.
-   [ ] Ensure the live data from QuestDB is streamed correctly and the chart animation remains smooth.
-   [ ] Once verified, the CSV reading logic can be removed from the Go service.

---
