"""HTTP API, and the built dashboard when STATIC_DIR is set."""

import base64
import binascii
import secrets

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from stockintel import queries
from stockintel.charts import TIMEFRAMES
from stockintel.config import get_settings
from stockintel.db import get_engine
from stockintel.factors import register
from stockintel.status import get_status

settings = get_settings()
if settings.app_env == "production" and not settings.dashboard_password:
    raise RuntimeError("DASHBOARD_PASSWORD must be set in production")

app = FastAPI(title="Stock Intelligence Platform", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["GET"],
)


def password_matches(header: str | None) -> bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header.removeprefix("Basic "), validate=True).decode()
    except (binascii.Error, UnicodeDecodeError):
        return False
    supplied = decoded.partition(":")[2]
    return secrets.compare_digest(supplied.encode(), get_settings().dashboard_password.encode())


@app.middleware("http")
async def require_password(request: Request, call_next):
    protected = get_settings().dashboard_password and request.url.path != "/api/health"
    if protected and not password_matches(request.headers.get("authorization")):
        return Response(
            status_code=401, headers={"WWW-Authenticate": 'Basic realm="Stock Intelligence"'}
        )
    return await call_next(request)


@app.get("/api/health")
def health() -> dict:
    """The API process is running. Says nothing about its dependencies."""
    return {"status": "ok"}


@app.get("/api/status")
def status() -> JSONResponse:
    """Full system state. Returns 503 when any part is unhealthy."""
    result = get_status(get_engine(), get_settings().worker_stale_after_seconds)
    return JSONResponse(result, status_code=200 if result["healthy"] else 503)


@app.get("/api/feeds")
def feeds() -> list[dict]:
    return queries.feeds(get_engine())


@app.get("/api/stocks")
def search(q: str = "") -> list[dict]:
    return queries.search(get_engine(), q.strip())


@app.get("/api/stocks/{ticker}")
def stock(ticker: str) -> dict:
    result = queries.stock(get_engine(), ticker)
    if result is None:
        raise HTTPException(404, "Not verified: this stock is not in the covered list")
    return result


@app.get("/api/stocks/{ticker}/chart")
def chart(ticker: str, timeframe: str = "daily") -> dict:
    if timeframe not in TIMEFRAMES:
        raise HTTPException(422, "timeframe must be daily, weekly or monthly")
    result = queries.chart(get_engine(), ticker, timeframe)
    if result is None:
        raise HTTPException(404, "Not verified: this stock is not in the covered list")
    return result


@app.get("/api/economic")
def economic() -> list[dict]:
    return queries.economic(get_engine())


@app.get("/api/backtest")
def backtest() -> dict | None:
    return queries.latest_backtest(get_engine())


@app.get("/api/stocks/{ticker}/forecast")
def forecast(ticker: str) -> dict | None:
    return queries.stock_forecast(get_engine(), ticker)


@app.get("/api/stocks/{ticker}/story")
def story(ticker: str) -> list[dict]:
    result = queries.stock_story(get_engine(), ticker)
    if result is None:
        raise HTTPException(404, "Not verified: this stock is not in the covered list")
    return result


@app.get("/api/ideas")
def ideas() -> dict:
    return queries.ideas(get_engine())


@app.get("/api/track-record")
def track_record() -> dict:
    return queries.track_record(get_engine())


@app.get("/api/factors")
def factor_register() -> list[dict]:
    return register()


@app.get("/api/issues")
def issues() -> list[dict]:
    return queries.issues(get_engine())


if settings.static_dir:
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="dashboard")
