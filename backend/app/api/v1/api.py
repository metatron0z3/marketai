from fastapi import APIRouter

from .endpoints import instruments, market_data, ingest

api_router = APIRouter()
api_router.include_router(instruments.router, prefix="/instruments", tags=["instruments"])
api_router.include_router(market_data.router, prefix="/market-data", tags=["market-data"])
api_router.include_router(ingest.router, prefix="/ingest", tags=["ingest"])
