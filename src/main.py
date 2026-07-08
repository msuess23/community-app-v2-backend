from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.core.config import settings
from src.core.exceptions import DomainException, domain_exception_handler
from src.core.scheduler import setup_scheduler, shutdown_scheduler
from src.core.limiter import limiter

import src.auth.models
import src.user.models
import src.office.models

from src.auth.router import router as auth_router
from src.user.router import router as user_router
from src.office.router import router as office_router

@asynccontextmanager
async def lifespan(app: FastAPI):
  """
  Manages the application lifecycle, including background tasks.
  """
  setup_scheduler()
  
  yield 
  
  shutdown_scheduler()

# Initialize the FastAPI application
app = FastAPI(
  title=settings.PROJECT_NAME,
  openapi_url=f"{settings.BASE_URL}/openapi.json",
  lifespan=lifespan
)

# Configure CORS (Cross-Origin Resource Sharing)
# For development, we allow all origins. In production, this should be restricted.
app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

app.state.limiter = limiter
# Register the global domain exception handler
app.add_exception_handler(DomainException, domain_exception_handler)
app.add_middleware(SlowAPIMiddleware)

# --- Router Registration ---
app.include_router(
  auth_router, 
  prefix=f"{settings.BASE_URL}/auth", 
  tags=["Authentication"]
)

app.include_router(
  user_router,
  prefix=f"{settings.BASE_URL}/users",
  tags=["Users"]
)

app.include_router(
  office_router,
  prefix=f"{settings.BASE_URL}/offices",
  tags=["Offices"]
)

@app.get("/")
async def root():
  """
  Health check and root endpoint.
  """
  return {
    "message": f"Welcome to the {settings.PROJECT_NAME} API",
    "status": "online"
  }