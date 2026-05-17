from fastapi import APIRouter

from .api.ingest import router as ingest_router
from .api.features import router as features_router
from .api.labels import router as labels_router
from .api.predictions import router as predictions_router

options_router = APIRouter(tags=["options"])
options_router.include_router(ingest_router)
options_router.include_router(features_router)
options_router.include_router(labels_router)
options_router.include_router(predictions_router)
