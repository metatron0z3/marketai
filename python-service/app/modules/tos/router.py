"""TOS module router — aggregates signals, chain, and score sub-routers."""
from fastapi import APIRouter

from app.modules.tos.api.chain import router as chain_router
from app.modules.tos.api.score import router as score_router
from app.modules.tos.api.signals import router as signals_router

tos_router = APIRouter(prefix="/tos", tags=["TOS Options"])

tos_router.include_router(signals_router)
tos_router.include_router(chain_router)
tos_router.include_router(score_router)
