from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.core.exceptions import DomainException, domain_exception_handler

import src.user.models
import src.office.models
import src.auth.models

from src.auth.router import router as auth_router
from src.user.router import router as user_router

# Initialize the FastAPI application
app = FastAPI(
  title=settings.PROJECT_NAME,
  openapi_url=f"{settings.BASE_URL}/openapi.json"
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

# Register the global domain exception handler
app.add_exception_handler(DomainException, domain_exception_handler)

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

@app.get("/")
async def root():
  """
  Health check and root endpoint.
  """
  return {
    "message": f"Welcome to the {settings.PROJECT_NAME} API",
    "status": "online"
  }