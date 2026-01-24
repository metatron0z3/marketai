import logging
import json
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Optional, Union
from datetime import date

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
async def get_market_data(
    instrument_id: int = Query(..., description="The instrument ID to query"),
    timeframe: str = Query(
        "5min", description="Aggregation timeframe: '5min', '1hour', or '1day'"
    ),
    start_date: Optional[date] = Query(
        None, description="Start date for filtering (YYYY-MM-DD)"
    ),
    end_date: Optional[date] = Query(
        None, description="End date for filtering (YYYY-MM-DD)"
    ),
) -> List[Dict[str, Union[str, int, float, None]]]:
    """
    Fetch market data from a static JSON file based on instrument.
    """
    try:
        logger.info(
            f"Fetching market data for instrument {instrument_id} with timeframe {timeframe} from static JSON."
        )

        # Path to the static JSON file
        json_file_path = "app/models/static_data/ohlcv_data.json"

        with open(json_file_path, 'r') as f:
            data = json.load(f)

        if not data:
            logger.info("Static JSON is empty.")
            return []

        # Filter by instrument_id
        filtered_data = [record for record in data if record.get('instrument_id') == instrument_id]

        if not filtered_data:
            logger.info(f"No market data found for instrument {instrument_id} in static JSON.")
            return []

        logger.info(f"Returning {len(filtered_data)} records of market data from static JSON.")
        return filtered_data

    except FileNotFoundError:
        logger.exception("The ohlcv_data.json file was not found.")
        raise HTTPException(status_code=404, detail="Market data file not found.")
    except Exception as e:
        logger.exception("Error fetching market data from static JSON:")
        raise HTTPException(status_code=500, detail="Internal server error.")