import pandas as pd
import math


def _clean(val):
    """Convert NaN/inf to None for JSON serialization."""
    if val is None:
        return None
    try:
        if math.isnan(val) or math.isinf(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def calc_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Calculate RSI using Wilder's smoothing method."""
    close = df["close"]
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Wilder's smoothing via EWM with alpha = 1/period
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    # Force NaN for rows before the period is filled
    rsi.iloc[:period] = float("nan")

    result = pd.DataFrame({"timestamp": df["timestamp"], "rsi": rsi})
    return result


def calc_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate VWAP (Volume Weighted Average Price)."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cum_tp_vol = (typical_price * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum()
    vwap = cum_tp_vol / cum_vol

    result = pd.DataFrame({"timestamp": df["timestamp"], "vwap": vwap})
    return result


def calc_ma(df: pd.DataFrame, period: int) -> pd.DataFrame:
    """Calculate Simple Moving Average."""
    ma = df["close"].rolling(window=period, min_periods=period).mean()
    result = pd.DataFrame({"timestamp": df["timestamp"], "ma": ma})
    return result


def calc_bollinger_bands(
    df: pd.DataFrame, period: int = 20, std_dev: float = 2.0
) -> pd.DataFrame:
    """Calculate Bollinger Bands."""
    rolling = df["close"].rolling(window=period, min_periods=period)
    middle = rolling.mean()
    std = rolling.std(ddof=1)  # Sample standard deviation
    upper = middle + std_dev * std
    lower = middle - std_dev * std

    result = pd.DataFrame(
        {
            "timestamp": df["timestamp"],
            "middle": middle,
            "upper": upper,
            "lower": lower,
        }
    )
    return result


def calc_volume(df: pd.DataFrame) -> pd.DataFrame:
    """Return volume per candle."""
    result = pd.DataFrame({"timestamp": df["timestamp"], "volume": df["volume"]})
    return result


def df_to_records(df: pd.DataFrame, value_columns: list) -> list:
    """Serialize a DataFrame to a list of dicts, converting NaN to None."""
    records = []
    for _, row in df.iterrows():
        record = {"timestamp": row["timestamp"]}
        for col in value_columns:
            record[col] = _clean(row[col])
        records.append(record)
    return records
