"""
Central configuration for the TOS collector.
All flows and collectors import WATCHLIST from here — one place to add tickers.
"""

WATCHLIST = [
    # Index ETFs — macro/regime context
    "SPY",   # SPDR S&P 500 ETF — most liquid options market, 0DTE dominant
    "QQQ",   # Invesco Nasdaq-100 — tech/growth sentiment leading indicator

    # MAG7 (6 of 7 — GOOGL not yet added)
    "TSLA",  # Tesla — highest retail options volume, primary ML training ticker
    "NVDA",  # NVIDIA — AI infrastructure, largest sweeps, best signal quality
    "AAPL",  # Apple — largest market cap, institutional hedging flow
    "MSFT",  # Microsoft — cloud/AI, clean institutional sweep signal
    "AMZN",  # Amazon — AWS + retail, high beta to macro
    "META",  # Meta — social/ad/AI, high retail interest + good sweep activity

    # Semiconductors — sector contagion pair
    "AMD",   # Advanced Micro Devices — NVDA competitor, contagion signal

    # Defense / Government Tech
    "PLTR",  # Palantir — retail darling, high unusual volume hit rate, AI/defense

    # Macro hedges / alternatives
    "GLD",   # SPDR Gold — risk-off sentiment, inflation hedge
    "TLT",   # iShares 20yr Treasury — rate leading indicator, macro regime
]

# Tickers to consider adding (not yet active)
WATCHLIST_CANDIDATES = [
    "GOOGL",  # Alphabet — completes MAG7
    "SMCI",   # Super Micro Computer — high beta to NVDA/AI narrative
    "MSTR",   # MicroStrategy — Bitcoin proxy, extreme gamma squeeze candidate
    "IWM",    # iShares Russell 2000 — small-cap risk-on/off indicator
]

# Schwab API constraints
INTRADAY_MAX_DAYS_PER_CALL = 10   # Schwab limit for minute-level bars
CHAIN_MAX_DTE              = 90   # only collect contracts within this DTE
CHAIN_MIN_DTE              = 1

# Unusual volume detection thresholds
UV_VOLUME_RATIO_THRESHOLD  = 3.0
UV_MIN_VOLUME              = 500
UV_MIN_PREMIUM             = 50_000
