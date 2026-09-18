from fastapi import FastAPI
from app.database import init_db
from app.routes.tasks import router as tasks_router
from app.routes.health import router as health_router
from app.config import APP_NAME, APP_ENV

app = FastAPI(
    title=APP_NAME,
    description="A simple Task Manager API for DevOps agent testing",
    version="1.0.0",
)

app.include_router(health_router, tags=["health"])
app.include_router(tasks_router, prefix="/tasks", tags=["tasks"])


@app.on_event("startup")
def startup_event():
    init_db()


@app.get("/")
def root():
    return {"app": APP_NAME, "env": APP_ENV, "status": "running"}
