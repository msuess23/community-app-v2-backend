import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


os.environ.setdefault("PROJECT_NAME", "Community Backend Test")
os.environ.setdefault("BASE_URL", "/api/v1")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("RUN_SEED_ON_STARTUP", "false")
os.environ.setdefault("ENABLE_SCHEDULER", "false")
os.environ.setdefault("CORS_ORIGINS", '["http://testserver"]')
