from fastapi import APIRouter, HTTPException, Query

from app.modules.options.services.labels import generate_labels

router = APIRouter()


@router.post("/labels/generate")
def generate_options_labels(
    symbol: str = Query(..., description="Underlying ticker symbol"),
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    data_source: str = Query(
        default="databento",
        description="Equity price source: 'databento' (trades_data) or 'massive' (underlying_bars)",
        pattern="^(databento|massive)$",
    ),
):
    try:
        count = generate_labels(symbol, start_date, end_date, data_source=data_source)
        return {"status": "ok", "labels_written": count, "symbol": symbol, "data_source": data_source}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
