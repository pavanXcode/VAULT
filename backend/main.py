"""
VAULT Backend Application Entrypoint.
Offline-first, private AI development platform backend.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import time
import uuid
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.api import api_router
from backend.config import get_settings
from backend.database import init_db
from backend.logging_config import setup_logging

settings = get_settings()
logger = setup_logging(log_level=settings.log_level, log_format=settings.log_format)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown routines."""
    logger.info(
        f"Starting {settings.app_name} v{settings.app_version}",
        extra={
            "environment": settings.environment,
            "offline_mode": settings.offline_mode,
            "database_url": settings.database_url,
            "llm_mode": settings.llm_mode,
            "llm_endpoint": settings.llm_endpoint,
        },
    )

    # 1. Initialize DB schema
    try:
        init_db()
        logger.info("Database schema initialized.")
    except Exception as exc:
        logger.error(f"Failed to initialize database schema: {exc}", exc_info=True)

    # 2. Ensure upload storage directory is ready
    settings.resolved_upload_path
    logger.info(f"Upload directory initialized at: {settings.resolved_upload_path}")

    # 3. Recover any jobs interrupted by a previous restart
    try:
        from backend.database import SessionLocal
        from backend.services.tool_execution_service import ToolExecutionService

        with SessionLocal() as db:
            recovered = ToolExecutionService.recover_interrupted_jobs(db)
            if recovered > 0:
                logger.info(f"Marked {recovered} orphaned running/pending jobs as interrupted.")
    except Exception as exc:
        logger.error(f"Failed to run job recovery on startup: {exc}", exc_info=True)

    yield

    logger.info(f"Shutting down {settings.app_name}.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="VAULT: Private, Offline-first AI Development Platform Backend.",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
    lifespan=lifespan,
)

# Configure CORS
origins = settings.cors_origins if isinstance(settings.cors_origins, list) else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Structured Request Logging and Timing Middleware
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:10])
    start_time = time.perf_counter()

    # Bind request context
    request.state.request_id = request_id
    client_ip = request.client.host if request.client else "unknown"

    try:
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Attach standard headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{duration_ms}ms"

        # Exclude high-frequency health checks from verbose logging if desired
        logger.info(
            f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
            },
        )
        return response
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.error(
            f"Unhandled exception during {request.method} {request.url.path}: {exc}",
            exc_info=True,
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
            },
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An internal server error occurred.",
                "request_id": request_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            headers={"X-Request-ID": request_id},
        )


# Custom Validation Error Handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", uuid.uuid4().hex[:10])
    errors = exc.errors()
    logger.warning(
        f"Validation failed for {request.method} {request.url.path}: {len(errors)} issues",
        extra={"request_id": request_id, "errors": str(errors)},
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "detail": jsonable_encoder(errors),
            "status_code": 422,
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        headers={"X-Request-ID": request_id},
    )


# Custom HTTP Exception Handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", uuid.uuid4().hex[:10])
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "status_code": exc.status_code,
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        headers={"X-Request-ID": request_id},
    )


# Mount unified API Router under /api
app.include_router(api_router, prefix="/api")


@app.get("/", tags=["Root"])
def root():
    """Root redirect / index for VAULT API."""
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "status": "online",
        "offline_mode": settings.offline_mode,
        "docs_url": "/docs",
        "api_prefix": "/api",
    }
