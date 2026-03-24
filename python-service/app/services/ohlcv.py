import pandas as pd
from typing import Optional
from ..core.db import get_db_connection

TIMEFRAME_MAP = {
    "5min": "5m",
    "1hour": "1h",
    "1day": "1d",
}


def fetch_ohlcv(
    instrument_id: int,
    timeframe: str = "5min",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch OHLCV candles from QuestDB and return as a DataFrame.
    Columns: timestamp (ISO string), open, high, low, close, volume.
    Returns empty DataFrame if no results.
    """
    sample_interval = TIMEFRAME_MAP.get(timeframe, "5m")

    query = f"""
        SELECT
            ts_event as timestamp,
            first(price) as open,
            max(price) as high,
            min(price) as low,
            last(price) as close,
            sum(size) as volume
        FROM trades_data
        WHERE instrument_id = {instrument_id}
    """

    if start_date:
        query += f" AND ts_event >= '{start_date}T00:00:00.000000Z'"
    if end_date:
        query += f" AND ts_event <= '{end_date}T23:59:59.999999Z'"

    query += f" SAMPLE BY {sample_interval} ALIGN TO CALENDAR"

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query)
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        return pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )

    df = pd.DataFrame(rows, columns=columns)

    # Normalize timestamp to ISO string with Z suffix
    df["timestamp"] = df["timestamp"].apply(
        lambda v: v.isoformat() + "Z" if hasattr(v, "isoformat") else str(v)
    )

    return df
