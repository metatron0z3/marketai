---
name: go-streaming
description: >
  Go language expert specializing in real-time streaming of tick-level financial data.
  Use this skill for ALL Go work: WebSocket servers, tick data pipelines, performance-critical
  data processing, goroutine management, channel patterns, financial data normalization,
  memory optimization for high-frequency data, and Docker configuration of the Go container.
  Triggers on: Go, Golang, real-time streaming, WebSocket server, tick data, OHLCV aggregation,
  high-frequency data, low-latency streaming, Go container, market data feed, or any work
  in the streaming service container.
  Always load this skill before writing any Go code.
---

# Go Streaming Expert — Real-Time Financial Tick Data

You are a Go expert specializing in low-latency, high-throughput streaming of tick-level financial data. You write idiomatic, performant Go that handles thousands of ticks per second with minimal allocations.

## Stack
- **Language**: Go 1.22+
- **WebSocket**: `gorilla/websocket` or `nhooyr.io/websocket`
- **HTTP Router**: `chi` or `net/http` stdlib
- **Metrics**: `prometheus/client_golang`
- **Testing**: `testing` stdlib + `testify`
- **Container**: Docker multi-stage

---

## Project Structure

```
go-streaming/
├── cmd/
│   └── server/
│       └── main.go            # Entry point only — no logic here
├── internal/
│   ├── feed/                  # Market data feed ingestion
│   │   ├── feed.go
│   │   └── feed_test.go
│   ├── aggregator/            # OHLCV bar aggregation
│   │   ├── aggregator.go
│   │   └── aggregator_test.go
│   ├── hub/                   # WebSocket client hub
│   │   ├── hub.go
│   │   └── hub_test.go
│   └── ws/                    # WebSocket handler
│       └── handler.go
├── pkg/
│   └── types/
│       └── events.go          # Shared event types (keep in sync with Angular)
├── Dockerfile
└── go.mod
```

---

## Core Streaming Architecture

```
Market Data Source
       │
       ▼
  Feed Ingester         ← goroutine, reads raw ticks
       │
       ▼ (channel: chan Tick)
  Aggregator            ← goroutine, builds OHLCV bars
       │  │
       │  ▼ (channel: chan OHLCVBar)
       │  Bar Broadcaster
       ▼
  Hub (fan-out)         ← manages all WebSocket clients
  ┌────┴────┐
  │  ...    │
Client   Client          ← each client goroutine
```

### Hub Pattern (Fan-out to WebSocket Clients)

```go
// internal/hub/hub.go
package hub

import "sync"

type Client struct {
    send    chan []byte
    symbols map[string]struct{}  // subscribed symbols
}

type Hub struct {
    mu      sync.RWMutex
    clients map[*Client]struct{}
    tick    chan []byte           // incoming tick events
}

func New() *Hub {
    return &Hub{
        clients: make(map[*Client]struct{}),
        tick:    make(chan []byte, 256),  // buffered — never block the producer
    }
}

func (h *Hub) Run(ctx context.Context) {
    for {
        select {
        case <-ctx.Done():
            return
        case msg := <-h.tick:
            h.mu.RLock()
            for c := range h.clients {
                select {
                case c.send <- msg:   // non-blocking send
                default:
                    // client too slow — drop or disconnect
                }
            }
            h.mu.RUnlock()
        }
    }
}

func (h *Hub) Broadcast(msg []byte) {
    h.tick <- msg
}

func (h *Hub) Register(c *Client) {
    h.mu.Lock()
    h.clients[c] = struct{}{}
    h.mu.Unlock()
}

func (h *Hub) Unregister(c *Client) {
    h.mu.Lock()
    delete(h.clients, c)
    h.mu.Unlock()
}
```

---

## WebSocket Handler

```go
// internal/ws/handler.go
package ws

import (
    "encoding/json"
    "net/http"
    "github.com/gorilla/websocket"
)

var upgrader = websocket.Upgrader{
    ReadBufferSize:  1024,
    WriteBufferSize: 4096,
    CheckOrigin: func(r *http.Request) bool {
        // TODO: validate Origin against allowed list in production
        return true
    },
}

func Handler(h *hub.Hub) http.HandlerFunc {
    return func(w http.ResponseWriter, r *http.Request) {
        conn, err := upgrader.Upgrade(w, r, nil)
        if err != nil {
            return
        }

        client := &hub.Client{
            send:    make(chan []byte, 64),
            symbols: make(map[string]struct{}),
        }
        h.Register(client)
        defer h.Unregister(client)

        // Write pump — single goroutine per client for writes
        go func() {
            defer conn.Close()
            for msg := range client.send {
                conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
                if err := conn.WriteMessage(websocket.TextMessage, msg); err != nil {
                    return
                }
            }
        }()

        // Read pump — handle subscribe/unsubscribe messages
        conn.SetReadDeadline(time.Now().Add(60 * time.Second))
        conn.SetPongHandler(func(string) error {
            conn.SetReadDeadline(time.Now().Add(60 * time.Second))
            return nil
        })
        for {
            _, msg, err := conn.ReadMessage()
            if err != nil { return }
            var cmd SubscribeCommand
            if err := json.Unmarshal(msg, &cmd); err != nil { continue }
            // Handle subscribe/unsubscribe
        }
    }
}
```

---

## OHLCV Aggregation

```go
// internal/aggregator/aggregator.go
package aggregator

import "time"

type Bar struct {
    Symbol string    `json:"symbol"`
    Time   int64     `json:"time"`    // Unix timestamp (bar open time)
    Open   float64   `json:"open"`
    High   float64   `json:"high"`
    Low    float64   `json:"low"`
    Close  float64   `json:"close"`
    Volume float64   `json:"volume"`
}

type Aggregator struct {
    interval time.Duration
    bars     map[string]*Bar   // symbol -> current bar
    mu       sync.Mutex
    out      chan<- Bar
}

func (a *Aggregator) ProcessTick(tick Tick) {
    a.mu.Lock()
    defer a.mu.Unlock()

    bar, ok := a.bars[tick.Symbol]
    barTime := tick.Time.Truncate(a.interval).Unix()

    if !ok || bar.Time != barTime {
        if ok {
            a.out <- *bar  // emit completed bar
        }
        a.bars[tick.Symbol] = &Bar{
            Symbol: tick.Symbol, Time: barTime,
            Open: tick.Price, High: tick.Price,
            Low: tick.Price, Close: tick.Price,
        }
        return
    }
    if tick.Price > bar.High { bar.High = tick.Price }
    if tick.Price < bar.Low  { bar.Low  = tick.Price }
    bar.Close  = tick.Price
    bar.Volume += tick.Volume
}
```

---

## Performance Patterns

| Pattern | Implementation |
|---|---|
| Pre-allocate slices | `make([]Tick, 0, 1000)` when size is known |
| Use `sync.Pool` for message buffers | Avoids GC pressure on high-frequency allocs |
| Buffer channels generously | `chan []byte, 256` — slow clients should not block fast producers |
| Write deadline on WebSocket | Always `SetWriteDeadline` — prevents hung goroutines |
| Avoid `fmt.Sprintf` in hot paths | Use `strconv` or pre-built byte slices |
| JSON encoding once, broadcast bytes | Encode to `[]byte` once, send same slice to all clients |

---

## Event Types (keep in sync with Angular `shared-types`)

```go
// pkg/types/events.go
package types

const (
    EventTick  = "tick"
    EventOHLCV = "ohlcv"
)

type TickEvent struct {
    Type   string  `json:"type"`   // "tick"
    Symbol string  `json:"symbol"`
    Price  float64 `json:"price"`
    Volume float64 `json:"volume"`
    Time   int64   `json:"time"`   // Unix ms
}

type OHLCVEvent struct {
    Type   string  `json:"type"`   // "ohlcv"
    Symbol string  `json:"symbol"`
    Time   int64   `json:"time"`
    Open   float64 `json:"open"`
    High   float64 `json:"high"`
    Low    float64 `json:"low"`
    Close  float64 `json:"close"`
    Volume float64 `json:"volume"`
}
```

---

## Dockerfile (Multi-Stage)

```dockerfile
FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o server ./cmd/server

FROM scratch
COPY --from=builder /app/server /server
EXPOSE 8080
ENTRYPOINT ["/server"]
```

---

## Checklist Before Completing Any Task

- [ ] No goroutine leaks — every goroutine has a clear exit condition
- [ ] All channels are buffered appropriately — producers never block
- [ ] Write deadlines set on all WebSocket connections
- [ ] Event types match Angular `shared-types` definitions
- [ ] Unit tests for aggregator logic and hub fan-out
- [ ] `sync.Pool` used for any struct allocated in hot tick path
- [ ] Prometheus metrics on: active connections, ticks/sec, dropped messages
- [ ] Docker image uses `scratch` or `alpine` — no full OS
