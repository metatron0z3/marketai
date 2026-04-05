# Database Schema

## Tables

### `trades_data`

Raw tick-level market data from Databento ingestion.

```sql
CREATE TABLE IF NOT EXISTS trades_data (
    ts_recv TIMESTAMP,              -- Reception timestamp
    ts_event TIMESTAMP,             -- Event timestamp (partitioning key)
    rtype INT,                      -- Record type
    publisher_id INT,               -- Data publisher
    instrument_id INT,              -- Symbol ID (e.g., 15144 for SPY)
    action SYMBOL,                  -- Trade action
    side SYMBOL,                    -- BUY or SELL
    depth INT,                      -- Market depth
    price DOUBLE,                   -- Trade price
    size LONG,                      -- Trade size (volume)
    flags INT,                      -- Trade flags
    ts_in_delta LONG,               -- Timestamp delta
    sequence LONG                   -- Sequence number
) TIMESTAMP(ts_event) PARTITION BY DAY;
```

**Key Design Decisions**:
- **Partitioned by day**: Enables fast range queries and old data pruning
- **ts_event as timestamp**: Primary time index for OHLCV aggregations
- **instrument_id**: Enables efficient filtering by symbol
- **LONG for size/sequence**: Handles high-frequency tick volumes

## Symbol Mapping

| Symbol | instrument_id |
|--------|---------------|
| SPY    | 15144         |
| QQQ    | 13340         |
| TSLA   | 16244         |

## OHLCV Aggregation

NestJS and Python services query trades_data using `SAMPLE BY` for efficient OHLCV calculations:

```sql
SELECT 
    ts_event,
    instrument_id,
    first(price) as open,
    max(price) as high,
    min(price) as low,
    last(price) as close,
    sum(size) as volume
FROM trades_data
WHERE instrument_id = ? AND ts_event > ?
SAMPLE BY 5m;  -- 5-minute candlesticks
```

Supported timeframes: 5m, 1h, 1d

## Indexes

QuestDB automatically indexes:
- `instrument_id` for symbol filtering
- `ts_event` (partitioning key) for time-range queries
