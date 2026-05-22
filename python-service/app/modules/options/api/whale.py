from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.modules.options.services.whale_features import compute_whale_features
from app.modules.options.services.whale_labels import generate_whale_labels
from app.modules.options.services.whale_inference import whale_predict, whale_top_signals

router = APIRouter()


class WhaleSnapshot(BaseModel):
    symbol: str
    strike: float
    expiration: str
    put_call: str
    cluster_premium_total: float = 0.0
    cluster_size_max: int = 0
    cluster_trade_count: int = 0
    strike_concentration: float = 0.0
    avg_dte: int = 0
    otm_pct: float = 0.0
    avg_delta: float = 0.0
    premium_per_trade: float = 0.0
    vol_oi_ratio: float = 0.0
    iv_rank: float = 0.0
    accumulation_days: int = 0
    call_put_ratio: float = 0.0


@router.post("/features/compute")
def compute_features(
    symbol: str = Query(...),
    start_date: str = Query(...),
    end_date: str = Query(...),
):
    try:
        count = compute_whale_features(symbol, start_date, end_date)
        return {"status": "ok", "rows_written": count}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/labels/generate")
def generate_labels(
    symbol: str = Query(...),
    start_date: str = Query(...),
    end_date: str = Query(...),
    data_source: str = Query(
        default="databento",
        description="Equity price source: 'databento' (trades_data) or 'massive' (underlying_bars)",
        pattern="^(databento|massive)$",
    ),
):
    try:
        count = generate_whale_labels(symbol, start_date, end_date, data_source=data_source)
        return {"status": "ok", "rows_labeled": count, "data_source": data_source}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/predict")
def predict_whale(snapshot: WhaleSnapshot):
    try:
        result = whale_predict(snapshot.model_dump())
        return {**snapshot.model_dump(), **result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/signals")
def get_whale_signals(
    n: int = Query(default=20, ge=1, le=100),
    lookback_days: int = Query(default=5, ge=1, le=90),
):
    try:
        signals = whale_top_signals(n=n, lookback_days=lookback_days)
        return {"signals": signals, "count": len(signals)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
