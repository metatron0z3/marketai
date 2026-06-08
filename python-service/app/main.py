from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.db import get_db_connection
from .api.v1.api import api_router
from .modules.options.db.schema import (
    create_enrichment_tables,
    create_massive_tables,
    create_options_tables,
    create_whale_tables,
)
from .modules.agents.db.schema import create_agent_tables

app = FastAPI()


@app.on_event("startup")
def on_startup():
    try:
        create_options_tables()
    except Exception as exc:
        print(f"Warning: could not create options tables: {exc}")
    try:
        create_whale_tables()
    except Exception as exc:
        print(f"Warning: could not create whale tables: {exc}")
    try:
        create_massive_tables()
    except Exception as exc:
        print(f"Warning: could not create massive tables: {exc}")
    try:
        create_enrichment_tables()
    except Exception as exc:
        print(f"Warning: could not create enrichment tables: {exc}")
    try:
        create_agent_tables()
    except Exception as exc:
        print(f"Warning: could not create agent tables: {exc}")

# CORS Middleware
origins = [
    "http://localhost",
    "http://localhost:4200",
    "http://frontend",
    "http://frontend:80",
    "http://market_frontend",
    "http://market_frontend:80",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Welcome to the MarketAI FastAPI Backend!"}

@app.get("/db-status")
async def db_status():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        return {"status": "success", "message": "Successfully connected to QuestDB"}
    except Exception as e:
        return {"status": "error", "message": f"Failed to connect to QuestDB: {e}"}

