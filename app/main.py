import logging
import time
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.database import init_db
from app.routes.tasks import router as tasks_router
from app.routes.health import router as health_router
from app.config import APP_NAME, APP_ENV
from app.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title=APP_NAME,
    description="A simple Task Manager API for DevOps agent testing",
    version="1.0.0",
)

app.include_router(health_router, tags=["health"])
app.include_router(tasks_router, prefix="/tasks", tags=["tasks"])


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 2)
    level = logging.ERROR if response.status_code >= 500 else logging.INFO
    logger.log(
        level,
        "request",
        extra={
            "extra": {
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            }
        },
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_exception",
        exc_info=exc,
        extra={
            "extra": {
                "method": request.method,
                "path": request.url.path,
                "error_type": type(exc).__name__,
                "traceback": traceback.format_exc(),
            }
        },
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.on_event("startup")
def startup_event():
    init_db()
    logger.info("application_started", extra={"extra": {"app": APP_NAME, "env": APP_ENV}})


@app.get("/")
def root():
    return {"app": APP_NAME, "env": APP_ENV, "status": "running"}
