from fastapi import APIRouter, HTTPException, Query

from app.modules.options.services.features import compute_features

router = APIRouter()


@router.post("/features/compute")
def compute_options_features(
    symbol: str = Query(..., description="Underlying ticker symbol"),
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
):
    try:
        count = compute_features(symbol, start_date, end_date)
        return {"status": "ok", "rows_written": count, "symbol": symbol}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
