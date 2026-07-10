"""
FastAPI application entry point
"""

import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import check_db_connection, AsyncSessionLocal
from app.core.security import ZeroShotSecurityValidator
from app.core.audit import audit_worker
from app.db.seed import seed_database
from app.services.chat_service import set_validator
from app.api.controllers.auth_controller import router as auth_router
from app.api.controllers.chat_controller import router as chat_router
from app.api.controllers.sanitize_controller import router as sanitize_router
from app.api.controllers.admin_controller import router as admin_router
from app.api.controllers.reporting_controller import router as reporting_router
from app.api.controllers.threads_controller import router as threads_router
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("Starting SecureMCP Enterprise Backend v2.0")
    logger.info("=" * 60)

    # 1. Verify database connection (migrations are run by start.bat / CI before startup)
    await check_db_connection()
    logger.info("Database ready")

    # 2. Seed default roles and users (idempotent)
    async with AsyncSessionLocal() as db:
        await seed_database(db)

    # 3. Load ML security models
    logger.info("Loading ML security models...")
    start = time.time()
    try:
        validator = ZeroShotSecurityValidator(settings.security_level)
        set_validator(validator)
        logger.info(f"Models loaded in {time.time() - start:.2f}s — level: {settings.security_level.value}")
    except Exception as e:
        logger.error(f"Failed to load ML models: {e}")
        logger.error("Server will start but security validation will fail")

    # 4. Start background audit worker
    audit_task = asyncio.create_task(audit_worker(AsyncSessionLocal))
    logger.info("Audit worker started")

    logger.info("=" * 60)
    logger.info(f"Server ready on {settings.HOST}:{settings.PORT}")
    logger.info("=" * 60)

    yield

    # Shutdown
    audit_task.cancel()
    try:
        await audit_task
    except asyncio.CancelledError:
        pass
    logger.info("Audit worker stopped. Server shutting down.")


app = FastAPI(
    title="SecureMCP Enterprise API",
    description="Enterprise-grade prompt security pipeline with RBAC and audit logging",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(sanitize_router)
app.include_router(admin_router)
app.include_router(reporting_router)
app.include_router(threads_router)


@app.get("/")
async def root():
    return {
        "service": "SecureMCP Enterprise API",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


if __name__ == "__main__":
    import sys
    import os
    # Ensure the python-backend directory is on sys.path when running directly
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )
