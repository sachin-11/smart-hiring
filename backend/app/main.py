import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import close_db, engine, init_db
from app.core.redis_client import check_redis_connection, close_redis_pool
from app.services.monitoring import PrometheusMiddleware, get_metrics_response

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting %s (%s environment)", settings.APP_NAME, settings.APP_ENV)
    try:
        await init_db()
    except Exception:
        logger.exception("Startup failed while initializing the database")
        raise
    yield
    logger.info("Shutting down %s", settings.APP_NAME)
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
