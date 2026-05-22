from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.modules.options.services.inference import predict, top_signals

router = APIRouter()


class ContractSnapshot(BaseModel):
    symbol: str
    strike: float
    expiration: str
    put_call: str
    rvol: float = 0.0
    vol_oi_ratio: float = 0.0
    premium_flow: float = 0.0
    sweep_intensity: float = 0.0
    aggressor_ratio: float = 0.0
    delta_exposure: float = 0.0
    iv_rank: float = 0.0
    days_to_exp: int = 0


@router.post("/predict")
def predict_signal(contract: ContractSnapshot):
    try:
        result = predict(contract.model_dump())
        return {**contract.model_dump(), **result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/signals")
def get_top_signals(
    n: int = Query(default=20, ge=1, le=100),
    lookback_minutes: int = Query(default=30, ge=1, le=1440),
):
    try:
        signals = top_signals(n=n, lookback_minutes=lookback_minutes)
        return {"signals": signals, "count": len(signals)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
