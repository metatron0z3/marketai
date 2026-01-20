-- Databento trades_data Data Quality Validation Queries for QuestDB
-- Assumes table name: trades_data
-- Common columns: ts_event, instrument_id, price, size, exchange, side, trade_id

-- =============================================================================
-- 1. TIMESTAMP VALIDATION
-- =============================================================================

-- Check for missing or null timestamps
SELECT 
    COUNT(*) as total_records,
    COUNT(ts_event) as valid_timestamps,
    COUNT(*) - COUNT(ts_event) as null_timestamps,
    ROUND(100.0 * (COUNT(*) - COUNT(ts_event)) / COUNT(*), 2) as null_timestamp_pct
FROM trades_data;

-- Check timestamp chronological order violations by instrument_id
SELECT 
    instrument_id,
    COUNT(*) as order_violations,
    MIN(ts_event) as first_violation_time,
    MAX(ts_event) as last_violation_time
FROM (
    SELECT 
        instrument_id,
        ts_event,
        LAG(ts_event) OVER (PARTITION BY instrument_id ORDER BY ts_event) as prev_ts
    FROM trades_data
) t
WHERE ts_event < prev_ts
GROUP BY instrument_id
ORDER BY order_violations DESC;

-- Find duplicate timestamps within instrument_id
SELECT 
    instrument_id,
    ts_event,
    COUNT(*) as duplicate_count
FROM trades_data
GROUP BY instrument_id, ts_event
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, instrument_id, ts_event;

-- Identify unusual timestamp gaps (>1 hour during trading hours)
SELECT 
    instrument_id,
    ts_event,
    prev_ts,
    (ts_event - prev_ts) / 1000000 as gap_ms,
    (ts_event - prev_ts) / 1000000000 as gap_seconds
FROM (
    SELECT 
        instrument_id,
        ts_event,
        LAG(ts_event) OVER (PARTITION BY instrument_id ORDER BY ts_event) as prev_ts
    FROM trades_data
    WHERE EXTRACT(hour FROM ts_event) BETWEEN 9 AND 16  -- Adjust for your trading hours
) t
WHERE (ts_event - prev_ts) > 3600000000000  -- 1 hour in nanoseconds
ORDER BY gap_seconds DESC;

-- =============================================================================
-- 2. PRICE AND SIZE VALIDATION
-- =============================================================================

-- Check for zero or negative prices
SELECT 
    instrument_id,
    COUNT(*) as invalid_price_count,
    MIN(price) as min_price,
    MAX(price) as max_price
FROM trades_data
WHERE price <= 0
GROUP BY instrument_id
ORDER BY invalid_price_count DESC;

-- Check for zero size trades_data
SELECT 
    instrument_id,
    exchange,
    COUNT(*) as zero_size_count,
    COUNT(*) * 100.0 / (SELECT COUNT(*) FROM trades_data WHERE trades_data.instrument_id = t.instrument_id) as zero_size_pct
FROM trades_data t
WHERE size = 0
GROUP BY instrument_id, exchange
ORDER BY zero_size_count DESC;

-- Identify price outliers using rolling statistics (3 standard deviations)
SELECT 
    instrument_id,
    ts_event,
    price,
    avg_price,
    stddev_price,
    ABS(price - avg_price) / stddev_price as z_score
FROM (
    SELECT 
        instrument_id,
        ts_event,
        price,
        AVG(price) OVER (
            PARTITION BY instrument_id 
            ORDER BY ts_event 
            ROWS BETWEEN 999 PRECEDING AND CURRENT ROW
        ) as avg_price,
        STDDEV(price) OVER (
            PARTITION BY instrument_id 
            ORDER BY ts_event 
            ROWS BETWEEN 999 PRECEDING AND CURRENT ROW
        ) as stddev_price
    FROM trades_data
) t
WHERE stddev_price > 0 
    AND ABS(price - avg_price) / stddev_price > 3
ORDER BY z_score DESC;

-- Volume outliers (unusually large trades_data)
SELECT 
    instrument_id,
    ts_event,
    size,
    avg_size,
    size / avg_size as size_ratio
FROM (
    SELECT 
        instrument_id,
        ts_event,
        size,
        AVG(size) OVER (
            PARTITION BY instrument_id 
            ORDER BY ts_event 
            ROWS BETWEEN 999 PRECEDING AND CURRENT ROW
        ) as avg_size
    FROM trades_data
    WHERE size > 0
) t
WHERE size > avg_size * 10  -- trades_data 10x larger than recent average
ORDER BY size_ratio DESC;

-- =============================================================================
-- 3. instrument_id AND EXCHANGE VALIDATION
-- =============================================================================

-- Check for unexpected exchange codes
SELECT 
    exchange,
    COUNT(*) as trade_count,
    COUNT(DISTINCT instrument_id) as unique_instrument_ids,
    MIN(ts_event) as first_trade,
    MAX(ts_event) as last_trade
FROM trades_data
GROUP BY exchange
ORDER BY trade_count DESC;

-- Identify instrument_ids with very few trades_data (potential data quality issues)
SELECT 
    instrument_id,
    exchange,
    COUNT(*) as trade_count,
    MIN(ts_event) as first_trade,
    MAX(ts_event) as last_trade,
    DATEDIFF('day', MIN(ts_event), MAX(ts_event)) as days_active
FROM trades_data
GROUP BY instrument_id, exchange
HAVING COUNT(*) < 10  -- instrument_ids with fewer than 10 trades_data
ORDER BY trade_count ASC;

-- Check for instrument_id case consistency issues
SELECT 
    UPPER(instrument_id) as instrument_id_upper,
    COUNT(DISTINCT instrument_id) as instrument_id_variations,
    STRING_AGG(DISTINCT instrument_id, ', ') as variations
FROM trades_data
GROUP BY UPPER(instrument_id)
HAVING COUNT(DISTINCT instrument_id) > 1;

-- =============================================================================
-- 4. EXACT DUPLICATE DETECTION
-- =============================================================================

-- Find exact duplicate trades_data
SELECT 
    instrument_id,
    ts_event,
    price,
    size,
    exchange,
    side,
    COUNT(*) as duplicate_count
FROM trades_data
GROUP BY instrument_id, ts_event, price, size, exchange, side
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;

-- =============================================================================
-- 5. DATA COMPLETENESS AND DISTRIBUTION CHECKS
-- =============================================================================

-- Overall data completeness check
SELECT 
    COUNT(*) as total_records,
    COUNT(DISTINCT instrument_id) as unique_instrument_ids,
    COUNT(DISTINCT exchange) as unique_exchanges,
    MIN(ts_event) as data_start,
    MAX(ts_event) as data_end,
    COUNT(CASE WHEN price IS NULL THEN 1 END) as null_prices,
    COUNT(CASE WHEN size IS NULL THEN 1 END) as null_sizes,
    COUNT(CASE WHEN instrument_id IS NULL THEN 1 END) as null_instrument_ids
FROM trades_data;

-- Trading activity by hour (identify gaps)
SELECT 
    EXTRACT(hour FROM ts_event) as hour,
    COUNT(*) as trade_count,
    COUNT(DISTINCT instrument_id) as active_instrument_ids,
    AVG(price) as avg_price,
    SUM(size) as total_volume
FROM trades_data
GROUP BY EXTRACT(hour FROM ts_event)
ORDER BY hour;

-- Daily trading summary (identify missing days)
SELECT 
    DATE(ts_event) as trade_date,
    COUNT(*) as trade_count,
    COUNT(DISTINCT instrument_id) as active_instrument_ids,
    MIN(price) as min_price,
    MAX(price) as max_price,
    SUM(size) as total_volume
FROM trades_data
GROUP BY DATE(ts_event)
ORDER BY trade_date;

-- =============================================================================
-- 6. PRICE CONTINUITY AND JUMP DETECTION
-- =============================================================================

-- Detect large price jumps (>5% between consecutive trades_data)
SELECT 
    instrument_id,
    ts_event,
    price,
    prev_price,
    ABS(price - prev_price) / prev_price as price_change_pct,
    (ts_event - prev_ts) / 1000000000 as time_gap_seconds
FROM (
    SELECT 
        instrument_id,
        ts_event,
        price,
        LAG(price) OVER (PARTITION BY instrument_id ORDER BY ts_event) as prev_price,
        LAG(ts_event) OVER (PARTITION BY instrument_id ORDER BY ts_event) as prev_ts
    FROM trades_data
    WHERE price > 0
) t
WHERE prev_price > 0 
    AND ABS(price - prev_price) / prev_price > 0.05  -- 5% price jump
ORDER BY price_change_pct DESC;

-- =============================================================================
-- 7. TRADE SIZE AND PATTERN ANALYSIS
-- =============================================================================

-- Identify potential wash trades_data (same price, similar size, close timing)
SELECT 
    instrument_id,
    price,
    ts_event,
    size,
    COUNT(*) as similar_trades_data,
    MAX(ts_event) - MIN(ts_event) as time_span_ns
FROM trades_data
GROUP BY instrument_id, price, CAST(ts_event / 1000000000 AS LONG), CAST(size / 100 AS LONG) * 100
HAVING COUNT(*) > 5  -- Multiple similar trades_data
    AND MAX(ts_event) - MIN(ts_event) < 60000000000  -- Within 60 seconds
ORDER BY similar_trades_data DESC;

-- =============================================================================
-- 8. DATA QUALITY SUMMARY REPORT
-- =============================================================================

-- Comprehensive data quality summary
SELECT 
    'Total Records' as metric,
    COUNT(*)::STRING as value,
    '' as percentage
FROM trades_data

UNION ALL

SELECT 
    'Unique instrument_ids' as metric,
    COUNT(DISTINCT instrument_id)::STRING as value,
    '' as percentage
FROM trades_data

UNION ALL

SELECT 
    'Records with Null Prices' as metric,
    COUNT(CASE WHEN price IS NULL THEN 1 END)::STRING as value,
    ROUND(100.0 * COUNT(CASE WHEN price IS NULL THEN 1 END) / COUNT(*), 2)::STRING || '%' as percentage
FROM trades_data

UNION ALL

SELECT 
    'Records with Zero/Negative Prices' as metric,
    COUNT(CASE WHEN price <= 0 THEN 1 END)::STRING as value,
    ROUND(100.0 * COUNT(CASE WHEN price <= 0 THEN 1 END) / COUNT(*), 2)::STRING || '%' as percentage
FROM trades_data

UNION ALL

SELECT 
    'Records with Zero Size' as metric,
    COUNT(CASE WHEN size = 0 THEN 1 END)::STRING as value,
    ROUND(100.0 * COUNT(CASE WHEN size = 0 THEN 1 END) / COUNT(*), 2)::STRING || '%' as percentage
FROM trades_data

UNION ALL

SELECT 
    'Date Range' as metric,
    DATE(MIN(ts_event))::STRING || ' to ' || DATE(MAX(ts_event))::STRING as value,
    DATEDIFF('day', MIN(ts_event), MAX(ts_event))::STRING || ' days' as percentage
FROM trades_data;