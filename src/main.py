from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.core.database import engine
from src.core.error_handlers import register_exception_handlers
from src.core.request_id import RequestIdMiddleware
from src.core.scheduler import setup_scheduler, shutdown_scheduler

import src.auth.models
import src.user.models
import src.office.models

from src.auth.router import router as auth_router
from src.user.router import router as user_router
from src.office.router import router as office_router


@asynccontextmanager
async def lifespan(app: FastAPI):
  """Start infrastructure components and always release them on shutdown."""
  setup_scheduler()
  try:
    yield
  finally:
    shutdown_scheduler()
    await engine.dispose()


app = FastAPI(
  title=settings.PROJECT_NAME,
  openapi_url=f"{settings.BASE_URL}/openapi.json",
  lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(
  auth_router,
  prefix=f"{settings.BASE_URL}/auth",
  tags=["Authentication"],
)

app.include_router(
  user_router,
  prefix=f"{settings.BASE_URL}/users",
  tags=["Users"],
)

app.include_router(
  office_router,
  prefix=f"{settings.BASE_URL}/offices",
  tags=["Offices"],
)


@app.get("/")
async def root():
  """Health check and root endpoint."""
  return {
    "message": f"Welcome to the {settings.PROJECT_NAME} API",
    "status": "online",
  }
