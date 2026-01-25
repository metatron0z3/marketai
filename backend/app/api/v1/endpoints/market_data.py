import logging
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Optional, Union
from datetime import date, datetime
from ....core.db import get_db_connection

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
async def get_market_data(
    instrument_id: int = Query(..., description="The instrument ID to query"),
    timeframe: str = Query(
        "5min", description="Aggregation timeframe: '5min', '1hour', or '1day'"
    ),
    start_date: Optional[str] = Query(
        None, description="Start date for filtering (YYYY-MM-DD)"
    ),
    end_date: Optional[str] = Query(
        None, description="End date for filtering (YYYY-MM-DD)"
    ),
) -> List[Dict[str, Union[str, int, float, None]]]:
    """
    Fetch aggregated OHLCV market data from QuestDB based on instrument and timeframe.
    """
    try:
        # Map timeframe to sample interval
        timeframe_map = {
            "5min": "5m",
            "1hour": "1h",
            "1day": "1d"
        }

        sample_interval = timeframe_map.get(timeframe, "5m")

        logger.info(
            f"Fetching market data from QuestDB: instrument={instrument_id}, "
            f"timeframe={timeframe}, start={start_date}, end={end_date}"
        )

        # Build the query
        query = f"""
        SELECT
            ts_event as timestamp,
            instrument_id,
            first(price) as open,
            max(price) as high,
            min(price) as low,
            last(price) as close,
            sum(size) as volume
        FROM trades_data
        WHERE instrument_id = {instrument_id}
        """

        # Add date filters if provided
        if start_date:
            query += f" AND ts_event >= '{start_date}T00:00:00.000000Z'"
        if end_date:
            query += f" AND ts_event <= '{end_date}T23:59:59.999999Z'"

        query += f"""
        SAMPLE BY {sample_interval}
        ALIGN TO CALENDAR
        """

        logger.info(f"Executing query: {query}")

        # Execute query
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query)

        # Fetch results
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        cursor.close()
        conn.close()

        # Convert to list of dictionaries
        result = []
        for row in rows:
            record = {}
            for i, col in enumerate(columns):
                value = row[i]
                # Convert timestamp to ISO string if it's a datetime
                if col == 'timestamp' and value:
                    if isinstance(value, datetime):
                        record[col] = value.isoformat() + 'Z'
                    else:
                        record[col] = str(value)
                else:
                    record[col] = value
            result.append(record)

        logger.info(f"Returning {len(result)} aggregated OHLCV records from QuestDB")
        return result

    except Exception as e:
        logger.exception(f"Error fetching market data from QuestDB: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")