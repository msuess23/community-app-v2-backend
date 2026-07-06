from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.core.exceptions import DomainException, domain_exception_handler

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
# We will include our domain routers here later. Example:
# from src.auth.router import router as auth_router
# app.include_router(auth_router, prefix=f"{settings.API_V1_STR}/auth", tags=["Authentication"])

@app.get("/")
async def root():
  """
  Health check and root endpoint.
  """
  return {
    "message": f"Welcome to the {settings.PROJECT_NAME} API",
    "status": "online"
  }