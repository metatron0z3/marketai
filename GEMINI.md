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

### Phase 1: Add Support & Resistance Lines to chart component
-   [ ] Find the frontend market-data component that draws a static chart
-   [ ] Create a component to work inside this one
-   [ ] Feature: When you mouse over the rendered chart, it creates a 2px, orange horizontal line across the x-axis at the vertical point
-   [ ] At the right edge of the chart should be displayed the precise price at that point. Price is displayed as the y-axis
-   [ ] IIf the user double-clicks, that orange line becoes permanent.
-   [ ] Save the price value of that line in a json file called support-resistance.json
-   [ ] The user should be able to set multiple lines in one chart



---
