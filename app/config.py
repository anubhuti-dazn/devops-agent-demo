import os

APP_NAME = os.getenv("APP_NAME", "devops-agent-demo")
APP_ENV = os.getenv("APP_ENV", "development")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tasks.db")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod")
MAX_TASKS_PER_USER = int(os.getenv("MAX_TASKS_PER_USER", "100"))
