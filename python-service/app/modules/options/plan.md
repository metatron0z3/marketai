 Here is Claude's plan:
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 Plan: Whale Positioning Detector (2-8 Week Institutional Options
 Signal)

 Context

 The existing options module detects short-term unusual volume —
 aggressive sweeps and urgent premium flow that precede a move within
 24 hours. The new feature targets a completely different behavior:
 institutional accumulation of medium-term options positions (2-8 week
 DTE) by whales who leg in slowly over multiple days to avoid
 detection, committing large dollar premiums to a directional view
 before a major catalyst.

 The two features share infrastructure (QuestDB connection, job
 manager, BaseFinancialModel, SequenceNormalizer, router) but have
 distinct tables, feature sets, labels, and model artifacts. They
 should never be confused in the codebase or by consumers of the API.

 ---
 How the Whale Feature Differs from the 24h Feature

 ┌────────────┬─────────────────────┬─────────────────────────────┐
 │ Dimension  │ 24h Unusual Volume  │   Whale Positioning (2-8    │
 │            │                     │            Week)            │
 ├────────────┼─────────────────────┼─────────────────────────────┤
 │ DTE filter │ Any expiration      │ 14–60 days only             │
 ├────────────┼─────────────────────┼─────────────────────────────┤
 │ Aggressor  │ All sides           │ BUY side only (calls or     │
 │ filter     │                     │ puts)                       │
 ├────────────┼─────────────────────┼─────────────────────────────┤
 │ Time       │ 5-minute            │ Daily                       │
 │ bucket     │                     │                             │
 ├────────────┼─────────────────────┼─────────────────────────────┤
 │ Signal     │ Urgency: sweep +    │ Accumulation: size +        │
 │ type       │ immediate           │ concentration over days     │
 │            │ aggression          │                             │
 ├────────────┼─────────────────────┼─────────────────────────────┤
 │ Premium    │ None                │ ≥ $25,000 per trade         │
 │ threshold  │                     │                             │
 ├────────────┼─────────────────────┼─────────────────────────────┤
 │ Key        │ sweep_intensity,    │ cluster_premium,            │
 │ signals    │ aggressor_ratio     │ strike_concentration,       │
 │            │                     │ accumulation_days           │
 ├────────────┼─────────────────────┼─────────────────────────────┤
 │ Label      │ 24 hours            │ 4 weeks (28 calendar days)  │
 │ horizon    │                     │                             │
 ├────────────┼─────────────────────┼─────────────────────────────┤
 │ Move       │ 2%                  │ 5%                          │
 │ threshold  │                     │                             │
 ├────────────┼─────────────────────┼─────────────────────────────┤
 │ Model      │ options_model.pt    │ whale_model.pt              │
 │ artifacts  │                     │                             │
 ├────────────┼─────────────────────┼─────────────────────────────┤
 │ API prefix │ /api/v1/options/*   │ /api/v1/options/whale/*     │
 └────────────┴─────────────────────┴─────────────────────────────┘

 ---
 New Files to Create

 All within python-service/app/modules/options/:

 db/schema.py               — ADD whale_trades + whale_features DDL
 services/whale_features.py — daily aggregation of whale-qualifying
 trades
 services/whale_labels.py   — label with 4-week >5% equity move
 services/whale_inference.py — model loader (@lru_cache) + signal
 ranking
 api/whale.py               — POST /whale/features/compute
                              POST /whale/predict
                              GET  /whale/signals
 ml/features/whale_feature_builder.py  — load labeled whale features
 from QuestDB
 ml/models/whale_model.py   — WHALE_FEATURE_COLS constant +
 LGBMWhaleModel
 ml/training/train_whale_lgbm.py       — Phase 1 training script
 router.py                  — MODIFY: include whale router at /whale
 prefix

 ---
 Stage 1 — QuestDB Schema (additions to db/schema.py)

 -- whale_trades: filtered raw options trades qualifying as potential
 whale activity
 -- Populated at feature-compute time from options_trades (not at
 ingest time)
 CREATE TABLE IF NOT EXISTS whale_trades (
     ts_event      TIMESTAMP,
     symbol        SYMBOL,
     strike        DOUBLE,
     expiration    DATE,
     put_call      SYMBOL,
     price         DOUBLE,
     size          LONG,
     premium       DOUBLE,       -- price × 100 × size
     delta         DOUBLE,
     iv            DOUBLE,
     open_interest LONG,
     days_to_exp   INT,
     otm_pct       DOUBLE        -- (strike - underlying_price) /
 underlying_price
 ) TIMESTAMP(ts_event) PARTITION BY DAY;

 -- whale_features: daily-bucketed whale positioning features per
 contract cluster
 CREATE TABLE IF NOT EXISTS whale_features (
     ts_event                TIMESTAMP,  -- trading day
     symbol                  SYMBOL,
     strike                  DOUBLE,
     expiration              DATE,
     put_call                SYMBOL,
     cluster_premium_total   DOUBLE,     -- total premium committed
 that day
     cluster_size_max        LONG,       -- largest single order in
 cluster
     cluster_trade_count     INT,        -- distinct buy trades in
 daily window
     strike_concentration    DOUBLE,     -- 1 - (std(strikes) /
 mean(strikes)); higher = more focused
     avg_dte                 INT,        -- average DTE of trades in
 cluster
     otm_pct                 DOUBLE,     -- average OTM% of cluster
     avg_delta               DOUBLE,     -- average delta of cluster
     premium_per_trade       DOUBLE,     -- cluster_premium_total /
 cluster_trade_count
     vol_oi_ratio            DOUBLE,     -- cluster size /
 open_interest
     iv_rank                 DOUBLE,     -- IV percentile vs 52-week
 range
     accumulation_days       INT,        -- distinct days with
 qualifying buys in past 5 days
     call_put_ratio          DOUBLE,     -- call premium / total
 premium (day-level, all symbols)
     label_4w                INT         -- 1 = underlying moved >5% in
  28 days, 0 = no, NULL = unlabeled
 ) TIMESTAMP(ts_event) PARTITION BY DAY;

 Modify: db/schema.py — add create_whale_tables(), call it from main.py
  startup alongside create_options_tables().

 ---
 Stage 2 — Feature Engineering (services/whale_features.py)

 Filter criteria applied to options_trades:
 - aggressor_side = 'BUY' — only buying activity
 - days_to_exp BETWEEN 14 AND 60 — institutional sweet spot for 2-8
 week plays
 - premium >= 25000 — minimum dollar commitment per trade (whale
 threshold)

 Aggregation window: daily (not 5-minute — whales accumulate over
 hours/days)

 Feature computation:

 ┌───────────────────────┬──────────────────────────────────────────┐
 │        Feature        │                 Formula                  │
 ├───────────────────────┼──────────────────────────────────────────┤
 │ cluster_premium_total │ SUM(premium) per (symbol, strike,        │
 │                       │ expiration, put_call, day)               │
 ├───────────────────────┼──────────────────────────────────────────┤
 │ cluster_size_max      │ MAX(size) in cluster                     │
 ├───────────────────────┼──────────────────────────────────────────┤
 │ cluster_trade_count   │ COUNT(*) in cluster                      │
 ├───────────────────────┼──────────────────────────────────────────┤
 │ strike_concentration  │ 1 - STDDEV(strike) / MEAN(strike) across │
 │                       │  all strikes per (symbol, day)           │
 ├───────────────────────┼──────────────────────────────────────────┤
 │ avg_dte               │ AVG(days_to_exp)                         │
 ├───────────────────────┼──────────────────────────────────────────┤
 │ otm_pct               │ Stored on whale_trades at filter time    │
 ├───────────────────────┼──────────────────────────────────────────┤
 │ avg_delta             │ AVG(delta)                               │
 ├───────────────────────┼──────────────────────────────────────────┤
 │ premium_per_trade     │ cluster_premium_total /                  │
 │                       │ cluster_trade_count                      │
 ├───────────────────────┼──────────────────────────────────────────┤
 │ vol_oi_ratio          │ SUM(size) / MAX(open_interest)           │
 ├───────────────────────┼──────────────────────────────────────────┤
 │ iv_rank               │ (AVG(iv) - MIN(iv over 52w)) / (MAX(iv   │
 │                       │ over 52w) - MIN(iv over 52w))            │
 ├───────────────────────┼──────────────────────────────────────────┤
 │                       │ Distinct days in past 5 calendar days    │
 │ accumulation_days     │ with qualifying buys for this (symbol,   │
 │                       │ strike, expiration, put_call)            │
 ├───────────────────────┼──────────────────────────────────────────┤
 │ call_put_ratio        │ Call premium / total premium across all  │
 │                       │ contracts for symbol on that day         │
 └───────────────────────┴──────────────────────────────────────────┘

 Endpoint: POST /api/v1/options/whale/features/compute?symbol=SPY&start
 _date=...&end_date=...

 ---
 Stage 3 — Label Generation (services/whale_labels.py)

 - For each whale_features row, fetch equity price from trades_data at
 ts_event and 28 days later
 - label_4w = 1 if abs(future_close_28d - price_now) / price_now > 0.05
 - Uses two batch queries + merge_asof (same pattern as existing
 services/labels.py — reuse that approach exactly)
 - No leakage: only future equity prices, never future IV/OI/options
 prices

 Endpoint: POST /api/v1/options/whale/labels/generate?symbol=SPY&start_
 date=...&end_date=...

 ---
 Stage 4 — ML Model (ml/models/whale_model.py)

 WHALE_FEATURE_COLS = [
     "cluster_premium_total", "cluster_size_max",
 "cluster_trade_count",
     "strike_concentration", "avg_dte", "otm_pct", "avg_delta",
     "premium_per_trade", "vol_oi_ratio", "iv_rank",
     "accumulation_days", "call_put_ratio",
 ]

 class LGBMWhaleModel(LGBMOptionsModel):
     """Inherits LGBMOptionsModel — same training loop, different
 feature space."""
     pass

 WHALE_FEATURE_COLS is the single source of truth — imported by
 whale_feature_builder.py, train_whale_lgbm.py, and whale_inference.py.

 ---
 Stage 5 — Training (ml/training/train_whale_lgbm.py)

 Follows the same pattern as train_lgbm.py exactly:
 - load_labeled_whale_features() from
 ml/features/whale_feature_builder.py
 - Walk-forward cross-validation via walk_forward_splits() (reuse from
 ml/evaluation/metrics.py)
 - SequenceNormalizer fit on train split only (reuse from
 ml/registry/model_registry.py)
 - LightGBM binary classifier
 - MLflow logging
 - Saves to whale_model.pkl + whale_model_normalizer.pkl in
 /app/artifacts/

 ---
 Stage 6 — Inference (services/whale_inference.py)

 Follows services/inference.py pattern exactly:
 - @lru_cache(maxsize=1) on model and normalizer loaders
 - Model path: whale_model.pt, normalizer path:
 whale_model_normalizer.pkl
 - Rule-based fallback: min((cluster_premium_total_normalized * 0.5 +
 accumulation_days_normalized * 0.3 + strike_concentration * 0.2), 1.0)
 - whale_top_signals(n, lookback_days) — queries whale_features over
 past N days (not minutes — whale signals are slower-moving)

 ---
 Stage 7 — API (api/whale.py)

 POST /api/v1/options/whale/features/compute  → compute & store whale
 features
 POST /api/v1/options/whale/labels/generate   → label whale_features
 rows
 POST /api/v1/options/whale/predict           → score a single whale
 snapshot
 GET  /api/v1/options/whale/signals           → top-N whale signals
 (lookback_days param)

 Note: lookback_days (not lookback_minutes) — whale signals accumulate
 over days, not minutes.

 ---
 Stage 8 — Router Update (router.py)

 from .api.whale import router as whale_router
 options_router.include_router(whale_router, prefix="/whale")

 ---
 Files to Modify

 ┌──────────────┬───────────────────────────────────────┐
 │     File     │                Change                 │
 ├──────────────┼───────────────────────────────────────┤
 │ db/schema.py │ Add create_whale_tables()             │
 ├──────────────┼───────────────────────────────────────┤
 │ app/main.py  │ Call create_whale_tables() at startup │
 ├──────────────┼───────────────────────────────────────┤
 │ router.py    │ Include whale_router at /whale prefix │
 └──────────────┴───────────────────────────────────────┘

 ---
 Infrastructure Reused (no changes needed)

 ┌───────────────────────────────┬──────────────────────────────────┐
 │             File              │          What's reused           │
 ├───────────────────────────────┼──────────────────────────────────┤
 │ app/core/db.py                │ get_db_connection()              │
 ├───────────────────────────────┼──────────────────────────────────┤
 │ app/core/job_manager.py       │ create_job, update_job           │
 ├───────────────────────────────┼──────────────────────────────────┤
 │ ml/models/base_model.py       │ BaseFinancialModel base class    │
 │                               │ pattern                          │
 ├───────────────────────────────┼──────────────────────────────────┤
 │ ml/models/lgbm_model.py       │ LGBMOptionsModel (subclassed by  │
 │                               │ LGBMWhaleModel)                  │
 ├───────────────────────────────┼──────────────────────────────────┤
 │ ml/registry/model_registry.py │ SequenceNormalizer,              │
 │                               │ save_normalizer, load_normalizer │
 ├───────────────────────────────┼──────────────────────────────────┤
 │ ml/evaluation/metrics.py      │ walk_forward_splits,             │
 │                               │ directional_accuracy             │
 ├───────────────────────────────┼──────────────────────────────────┤
 │ services/greeks.py            │ calculate_greeks() (used at      │
 │                               │ filter time)                     │
 ├───────────────────────────────┼──────────────────────────────────┤
 │                               │ Batch-query + merge_asof label   │
 │ services/labels.py            │ pattern (copied, not imported —  │
 │                               │ different table/threshold)       │
 └───────────────────────────────┴──────────────────────────────────┘

 ---
 Verification

 1. Run create_whale_tables() → verify whale_trades and whale_features
 appear in QuestDB (http://localhost:9000)
 2. Ingest OPRA data via existing /ingest/upload endpoint
 3. POST
 /api/v1/options/whale/features/compute?symbol=SPY&start_date=... →
 verify whale_features rows with non-null cluster_premium_total
 4. POST
 /api/v1/options/whale/labels/generate?symbol=SPY&start_date=... →
 verify label_4w populated (not all null)
 5. docker exec market_python_service python -m
 app.modules.options.ml.training.train_whale_lgbm → verify MLflow run
 logged
 6. POST /api/v1/options/whale/predict with sample snapshot → returns
 whale_signal_score
 7. GET /api/v1/options/whale/signals?n=10&lookback_days=5 → returns
 ranked whale signals distinct from /signals