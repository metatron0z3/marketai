from fastapi import APIRouter

from .endpoints import instruments, market_data, ingest, indicators, ingest_yfinance
from app.modules.options.router import options_router

api_router = APIRouter()
api_router.include_router(instruments.router,      prefix="/instruments",      tags=["instruments"])
api_router.include_router(market_data.router,      prefix="/market-data",      tags=["market-data"])
api_router.include_router(ingest.router,           prefix="/ingest",           tags=["ingest"])
api_router.include_router(ingest_yfinance.router,  prefix="/ingest/yfinance",  tags=["ingest"])
api_router.include_router(indicators.router,       prefix="/indicators",       tags=["indicators"])
api_router.include_router(options_router,          prefix="/options")
