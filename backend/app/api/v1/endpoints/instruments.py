from fastapi import APIRouter, HTTPException
from typing import List, Dict, Union

router = APIRouter()

# Hardcoded symbols for now, similar to the Streamlit app
SYMBOLS = {"SPY": 15144, "QQQ": 13340, "TSLA": 16244}

@router.get("/", response_model=List[Dict[str, Union[str, int]]])
async def get_instruments():
    """
    Get a list of available instruments (symbols and their IDs).
    """
    return [{"symbol": symbol, "id": id} for symbol, id in SYMBOLS.items()]
