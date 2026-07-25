import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import close_db, engine, init_db
from app.core.logging_config import configure_logging
from app.core.rate_limit import limiter
from app.core.redis_client import check_redis_connection, close_redis_pool
from app.core.security_headers import SecurityHeadersMiddleware
from app.services.mlops.scheduler import start_scheduler, stop_scheduler
from app.services.monitoring import PrometheusMiddleware, get_metrics_response

configure_logging(debug=settings.DEBUG, log_format=settings.LOG_FORMAT)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting %s (%s environment)", settings.APP_NAME, settings.APP_ENV)
    try:
        await init_db()
    except Exception:
        logger.exception("Startup failed while initializing the database")
        raise
    start_scheduler()
    yield
    logger.info("Shutting down %s", settings.APP_NAME)
    stop_scheduler()
    await close_db()
    await close_redis_pool()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(PrometheusMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    # Match the {"detail": ...} shape the rest of the API (and the frontend's
    # extractErrorMessage helper) expects, instead of slowapi's default {"error": ...}.
    return JSONResponse(status_code=429, content={"detail": f"Too many requests — {exc.detail}. Please try again shortly."})

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/metrics", tags=["monitoring"])
async def metrics():
    return get_metrics_response()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """Reports service, database, and Redis connectivity."""
    db_ok = True
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database health check failed")
        db_ok = False

    redis_ok = await check_redis_connection()

    status = "ok" if db_ok and redis_ok else "degraded"
    return {
        "status": status,
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "database": "ok" if db_ok else "unreachable",
        "redis": "ok" if redis_ok else "unreachable",
    }


@app.get("/", tags=["root"])
async def root() -> dict:
    return {"message": f"{settings.APP_NAME} API", "docs": "/docs"}
