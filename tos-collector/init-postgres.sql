-- TOS Postgres schema initialization
-- Runs on first container start via docker-entrypoint-initdb.d

-- signal_catalog: the primary ML training table
CREATE TABLE IF NOT EXISTS signal_catalog (
    signal_id                   VARCHAR(64) PRIMARY KEY,
    symbol                      VARCHAR(16) NOT NULL,
    option_type                 CHAR(1)     NOT NULL,
    strike                      FLOAT,
    expiry_date                 DATE,
    days_to_expiry              INT,
    detected_at                 TIMESTAMPTZ NOT NULL,
    moneyness                   VARCHAR(8),
    otm_pct                     FLOAT,
    volume                      INT,
    prior_snapshot_volume       INT,
    volume_delta                INT,
    avg_volume_10d              FLOAT,
    avg_volume_20d              FLOAT,
    volume_ratio_10d            FLOAT,
    volume_ratio_20d            FLOAT,
    open_interest               INT,
    vol_oi_ratio                FLOAT,
    bid                         FLOAT,
    ask                         FLOAT,
    mark                        FLOAT,
    ba_spread_pct               FLOAT,
    implied_vol                 FLOAT,
    iv_rank                     FLOAT,
    iv_percentile               FLOAT,
    delta                       FLOAT,
    gamma                       FLOAT,
    theta                       FLOAT,
    vega                        FLOAT,
    underlying_price            FLOAT,
    premium_total               FLOAT,
    notional_value              FLOAT,
    is_sweep                    BOOLEAN DEFAULT FALSE,
    is_call                     BOOLEAN,
    in_the_money                BOOLEAN DEFAULT FALSE,
    hour_of_day                 INT,
    is_morning                  BOOLEAN DEFAULT FALSE,
    is_afternoon                BOOLEAN DEFAULT FALSE,
    session                     VARCHAR(16),
    detection_method            VARCHAR(32),
    -- follow-through labels (filled by EOD label job)
    underlying_return_1d_fwd    FLOAT,
    underlying_return_5d_fwd    FLOAT,
    direction_correct_5d        INT,
    move_exceeded_2pct_5d       INT,
    quality_signal              INT,
    option_return_5d            FLOAT,
    -- precomputed historical ticker features (filled nightly)
    ticker_signal_hit_rate_30d  FLOAT,
    ticker_signal_count_30d     INT,
    ticker_avg_return_5d_after  FLOAT,
    ticker_avg_premium_30d      FLOAT,
    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signal_catalog_symbol       ON signal_catalog(symbol);
CREATE INDEX IF NOT EXISTS idx_signal_catalog_detected_at  ON signal_catalog(detected_at);
CREATE INDEX IF NOT EXISTS idx_signal_catalog_unlabeled    ON signal_catalog(detected_at)
    WHERE underlying_return_5d_fwd IS NULL;

-- conviction_scores: written by MarketAI batch scorer
CREATE TABLE IF NOT EXISTS conviction_scores (
    signal_id           VARCHAR(64) PRIMARY KEY REFERENCES signal_catalog(signal_id),
    symbol              VARCHAR(16) NOT NULL,
    option_type         CHAR(1),
    quality_score       FLOAT,
    direction_score     FLOAT,
    magnitude_score     FLOAT,
    regime              VARCHAR(32),
    regime_multiplier   FLOAT,
    conviction_score    FLOAT,
    sequence_quality    FLOAT,
    cluster_quality     FLOAT,
    scored_at           TIMESTAMPTZ DEFAULT NOW(),
    model_version       VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS idx_conviction_symbol    ON conviction_scores(symbol);
CREATE INDEX IF NOT EXISTS idx_conviction_score     ON conviction_scores(conviction_score DESC);

-- options_volume_baseline: rolling 20d average per contract
CREATE TABLE IF NOT EXISTS options_volume_baseline (
    symbol          VARCHAR(16)  NOT NULL,
    strike          FLOAT        NOT NULL,
    option_type     CHAR(1)      NOT NULL,
    expiry_date     DATE         NOT NULL,
    avg_volume_10d  FLOAT,
    avg_volume_20d  FLOAT,
    median_volume   FLOAT,
    n_days          INT,
    updated_at      TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (symbol, strike, option_type, expiry_date)
);

-- signal_clusters: multi-strike event groups
CREATE TABLE IF NOT EXISTS signal_clusters (
    cluster_id          VARCHAR(64) PRIMARY KEY,
    symbol              VARCHAR(16) NOT NULL,
    detected_at         TIMESTAMPTZ NOT NULL,
    contract_count      INT,
    call_count          INT,
    put_count           INT,
    total_premium       FLOAT,
    strike_dispersion   FLOAT,
    dte_range           INT,
    weighted_delta      FLOAT,
    is_call_dominant    BOOLEAN,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS signal_cluster_members (
    cluster_id  VARCHAR(64) REFERENCES signal_clusters(cluster_id),
    signal_id   VARCHAR(64) REFERENCES signal_catalog(signal_id),
    PRIMARY KEY (cluster_id, signal_id)
);

-- earnings_calendar
CREATE TABLE IF NOT EXISTS earnings_calendar (
    symbol          VARCHAR(16)  NOT NULL,
    earnings_date   DATE         NOT NULL,
    confirmed       BOOLEAN      DEFAULT FALSE,
    eps_estimate    FLOAT,
    updated_at      TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (symbol, earnings_date)
);

-- watchlist
CREATE TABLE IF NOT EXISTS watchlist (
    symbol          VARCHAR(16) PRIMARY KEY,
    name            VARCHAR(128),
    sector          VARCHAR(64),
    active          BOOLEAN DEFAULT TRUE,
    added_at        TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO watchlist (symbol, name, sector) VALUES
    ('TSLA', 'Tesla Inc.',              'EV/Consumer Discretionary'),
    ('NVDA', 'NVIDIA Corporation',      'Semiconductors'),
    ('SPY',  'SPDR S&P 500 ETF',        'Macro/Index'),
    ('QQQ',  'Invesco QQQ Trust',       'Macro/Index'),
    ('AAPL', 'Apple Inc.',              'Technology'),
    ('AMD',  'Advanced Micro Devices',  'Semiconductors'),
    ('META', 'Meta Platforms',          'Technology'),
    ('AMZN', 'Amazon.com Inc.',         'Technology/Consumer'),
    ('MSFT', 'Microsoft Corporation',   'Technology'),
    ('GLD',  'SPDR Gold Shares',        'Commodities'),
    ('TLT',  'iShares 20+ Year Treasury Bond ETF', 'Fixed Income/Macro'),
    ('PLTR', 'Palantir Technologies',  'Defense/Government Tech')
ON CONFLICT (symbol) DO NOTHING;
