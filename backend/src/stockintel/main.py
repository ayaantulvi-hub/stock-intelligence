"""HTTP API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from stockintel.config import get_settings
from stockintel.db import get_engine
from stockintel.status import get_status

app = FastAPI(title="Stock Intelligence Platform", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_methods=["GET"],
)


@app.get("/api/health")
def health() -> dict:
    """The API process is running. Says nothing about its dependencies."""
    return {"status": "ok"}


@app.get("/api/status")
def status() -> JSONResponse:
    """Full system state. Returns 503 when any part is unhealthy."""
    result = get_status(get_engine(), get_settings().worker_stale_after_seconds)
    return JSONResponse(result, status_code=200 if result["healthy"] else 503)
