from fastapi import APIRouter

from .endpoints import indicators, ingest, ingest_yfinance, instruments, market_data
from app.modules.llm.api.usage import router as llm_usage_router
from app.modules.options.router import options_router
from app.modules.tos.router import tos_router

api_router = APIRouter()
api_router.include_router(instruments.router,      prefix="/instruments",      tags=["instruments"])
api_router.include_router(market_data.router,      prefix="/market-data",      tags=["market-data"])
api_router.include_router(ingest.router,           prefix="/ingest",           tags=["ingest"])
api_router.include_router(ingest_yfinance.router,  prefix="/ingest/yfinance",  tags=["ingest"])
api_router.include_router(indicators.router,       prefix="/indicators",       tags=["indicators"])
api_router.include_router(options_router,          prefix="/options")
api_router.include_router(tos_router)
api_router.include_router(llm_usage_router,        prefix="/llm",              tags=["llm-observability"])
