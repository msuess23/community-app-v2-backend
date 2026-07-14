from __future__ import annotations

import os


TEST_ENV = {
  "PROJECT_NAME": "Community App Test",
  "BASE_URL": "/api/v1",
  "SECRET_KEY": "test-secret-key-that-is-longer-than-32-characters",
  "ACCESS_TOKEN_EXPIRE_MINUTES": "15",
  "REFRESH_TOKEN_EXPIRE_DAYS": "7",
  "POSTGRES_USER": "test",
  "POSTGRES_PASSWORD": "test",
  "POSTGRES_DB": "test",
  "POSTGRES_HOST": "localhost",
  "POSTGRES_PORT": "5432",
}

for key, value in TEST_ENV.items():
  os.environ.setdefault(key, value)
