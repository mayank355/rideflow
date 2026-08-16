import os
from fastapi import FastAPI
from sqlalchemy import create_engine, text
import redis

from app.database import Base, engine as db_engine
from app.core.logging_config import setup_logging, logger
from app.core.logging_middleware import RequestLoggingMiddleware
from app.models.driver import Driver  # noqa: F401 — import ensures table is registered with Base
from app.models.rider import Rider  # noqa: F401
from app.models.trip import Trip  # noqa: F401
from app.models.trip_location_log import TripLocationLog  # noqa: F401
from app.routers import drivers, riders, trips, auth
from app.websocket import routes as ws_routes

setup_logging()

app = FastAPI(title="RideFlow")
app.add_middleware(RequestLoggingMiddleware)

DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL")

engine = create_engine(DATABASE_URL)
redis_client = redis.from_url(REDIS_URL)

logger.info("RideFlow starting up")

DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL")

engine = create_engine(DATABASE_URL)
redis_client = redis.from_url(REDIS_URL)

# Schema is now managed by Alembic migrations (run `alembic upgrade head`
# before starting the app, or via docker-compose entrypoint), NOT
# create_all(). create_all() can only create missing tables — it cannot
# alter existing ones, which is exactly the limitation that forced manual
# table drops in earlier phases. Alembic tracks incremental changes
# safely, including on tables with real data.

app.include_router(auth.router)
app.include_router(drivers.router)
app.include_router(riders.router)
app.include_router(trips.router)
app.include_router(ws_routes.router)


@app.get("/")
def root():
    return {"message": "RideFlow is alive"}


@app.get("/health")
def health_check():
    """
    Proves Phase 0 works: FastAPI can reach both Postgres and Redis.
    This route gets deleted/replaced once real routes exist.
    """
    status = {"postgres": "unknown", "redis": "unknown"}

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        status["postgres"] = "connected"
    except Exception as e:
        status["postgres"] = f"failed: {str(e)}"

    try:
        redis_client.ping()
        status["redis"] = "connected"
    except Exception as e:
        status["redis"] = f"failed: {str(e)}"

    return status
