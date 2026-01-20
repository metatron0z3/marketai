from sqlalchemy import create_engine
import logging
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Optional, Union
from datetime import date
import pandas as pd
# from app.core.db import get_db_connection # This will be removed or commented out

logger = logging.getLogger(__name__)

router = APIRouter()

# QuestDB connection string for SQLAlchemy
QUESTDB_CONNECTION_STRING = "postgresql://admin:quest@questdb:8812/qdb"
engine = create_engine(QUESTDB_CONNECTION_STRING)

@router.get("/")
async def get_market_data(
    instrument_id: int = Query(..., description="The instrument ID to query"),
    timeframe: str = Query("5min", description="Aggregation timeframe: '5min', '1hour', or '1day'"),
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)")
) -> List[Dict[str, Union[str, int, float]]]: # Changed return type to be more flexible
    """
    Fetch market data from QuestDB based on instrument and timeframe.
    """
    try:
        logger.info(f"Fetching market data for instrument {instrument_id} with timeframe {timeframe}")
        
        # Map timeframe to aggregation interval
        timeframe_map = {"5min": "5m", "1hour": "1h", "1day": "1d"}
        interval = timeframe_map.get(timeframe, "5m")

        # Base query
        query = f"""
        SELECT 
            ts_event as timestamp,
            instrument_id,
            MAX(CASE WHEN side = 'B' THEN price END) as bid,
            MAX(CASE WHEN side = 'A' THEN price END) as ask,
            (MAX(CASE WHEN side = 'B' THEN price END) + MAX(CASE WHEN side = 'A' THEN price END)) / 2 as mid_price,
            MAX(CASE WHEN side = 'B' THEN size END) as bid_size,
            MAX(CASE WHEN side = 'A' THEN size END) as ask_size
        FROM trades_data
        WHERE instrument_id = {instrument_id}
        """

        if start_date:
            query += f" AND ts_event >= '{start_date}'"
        if end_date:
            query += f" AND ts_event <= '{end_date}'"

        query += " GROUP BY ts_event, instrument_id ORDER BY ts_event DESC LIMIT 10000"

        logger.info(f"Constructed SQL Query: {query}")
        df = pd.read_sql(query, engine) # Use the SQLAlchemy engine here

        if df.empty:
            logger.info("No market data found for the given parameters.")
            return []

        df["timestamp"] = pd.to_datetime(df["timestamp"])

        # Resample based on timeframe if needed
        if timeframe != "5min":
            df = df.set_index("timestamp")
            df = (
                df.resample(interval)
                .agg(
                    {
                        "bid": "last",
                        "ask": "last",
                        "mid_price": "last",
                        "bid_size": "sum",
                        "ask_size": "sum",
                    }
                )
                .dropna()
                .reset_index()
            )
        
        # Convert timestamp to string for JSON serialization
        df['timestamp'] = df['timestamp'].dt.isoformat()
        logger.info(f"Returning {len(df)} records of market data.")
        return df.to_dict(orient="records")

    except Exception as e:
        logger.exception("Error fetching market data:") # Keep the logger.exception
        raise HTTPException(status_code=500, detail=str(e))
    # finally: # Remove the finally block, engine handles connections
    #     if conn:
    #         conn.close()
