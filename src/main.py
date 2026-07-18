import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

# Import one explicit registry so SQLAlchemy sees every mapped table.
import src.models  # noqa: F401

from scripts.seed.run_seed import seed_database
from src.auth.router import router as auth_router
from src.core.config import settings
from src.core.database import engine
from src.core.error_handlers import (
  domain_exception_handler,
  http_exception_handler,
  integrity_error_handler,
  request_validation_exception_handler,
  unexpected_exception_handler,
)
from src.core.exceptions import DomainException
from src.core.scheduler import setup_scheduler, shutdown_scheduler
from src.office.router import router as office_router
from src.ticket.router import router as ticket_router
from src.user.router import router as user_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
  """Runs optional startup tasks and always releases background resources."""
  del app
  scheduler_started = False

  try:
    if settings.RUN_SEED_ON_STARTUP:
      logger.info("RUN_SEED_ON_STARTUP is enabled")
      await seed_database()

    if settings.ENABLE_SCHEDULER:
      setup_scheduler()
      scheduler_started = True
    else:
      logger.info("Background scheduler is disabled")

    yield
  finally:
    if scheduler_started:
      shutdown_scheduler()
    await engine.dispose()


app = FastAPI(
  title=settings.PROJECT_NAME,
  openapi_url=f"{settings.BASE_URL}/openapi.json",
  lifespan=lifespan,
)

app.add_middleware(
  CORSMiddleware,
  allow_origins=settings.CORS_ORIGINS,
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

app.add_exception_handler(DomainException, domain_exception_handler)
app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(IntegrityError, integrity_error_handler)
app.add_exception_handler(Exception, unexpected_exception_handler)

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
app.include_router(
  ticket_router,
  prefix=f"{settings.BASE_URL}/tickets",
  tags=["Tickets"],
)


@app.get("/")
async def root():
  return {
    "message": f"Welcome to the {settings.PROJECT_NAME} API",
    "status": "online",
  }
